#!/usr/bin/env python3
"""
Swarm-Doctor referee runner (v1).

Doctor before manager: triage a sick AI agent's HEALTH (not its answer quality),
then decide treat / observe / discharge to eval-curator.

Usage:
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --out receipts/visit.json

    # Run ONE real vitals probe and override the observed vitals with ground truth:
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe docker:swarmcore-postgres
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe systemctl:chrony.service

    # Roster & continuity: pair with a depth chart so a removed starter activates next-man-up.
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --depth-chart depth_chart.yaml

    # Self-test: run every example sheet and assert the expected discharge (+ coverage).
    python3 cli/swarm_doctor.py --selftest examples/sheets

The flight sheet is machine-readable instructions: thresholds, stability weights, and the
`observations` block for this visit. The runner computes health math, classifies findings
as HARD_FAULT or SOFT_WARNING, picks a root_cause_category, scores diagnosis confidence,
estimates time-to-recovery, decides if a human is required, and writes a sha256-stamped
JSON receipt ending in one of:

    TREATMENT_REQUIRED | OBSERVE | DISCHARGE_TO_EVAL_CURATOR

OFFLINE BY DEFAULT: this tool reads a local flight sheet and runs local probes only.
Source data never leaves the office. No network calls, no cloud, no telemetry.

It does NOT grade answer quality. That is eval-curator's job, only after discharge.

TODO(automation): pulse/bloodwork/neuro observations are filled by hand today. Vitals can
already be probed for real (--probe). Future work wires an HTTP probe for pulse, log
scraping for bloodwork, and model introspection for neuro. The math/decision stay the same.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("Swarm-Doctor needs PyYAML. Install with: pip install pyyaml")

SCHEMA_VERSION = "1.1"

# --- severities --------------------------------------------------------------
HARD_FAULT = "HARD_FAULT"     # blocks discharge; needs treatment
SOFT_WARNING = "SOFT_WARNING"  # alive but degraded; observe

# --- root cause taxonomy -----------------------------------------------------
ROOT_CAUSE_CATEGORIES = [
    "infra", "model", "retrieval", "tool_call",
    "prompt", "context", "network", "auth", "unknown",
]
# Most-upstream first: when several categories are faulted, this order picks the
# dominant one (a dead box "infra" outranks a prompt issue, etc.).
CATEGORY_PRIORITY = [
    "infra", "network", "auth", "model", "prompt", "context",
    "retrieval", "tool_call", "unknown",
]

HARD_VITALS = {"dead", "crash_loop", "unreachable", "hung"}

# Recognized bloodwork flags -> root cause category. All recognized flags are hard.
BLOODWORK_CATEGORY = {
    "oom": "infra",
    "cuda_error": "infra",
    "context_blowout": "context",
    "template_corruption": "prompt",
    "tool_call_failure": "tool_call",
    "auth_error": "auth",
    "retrieval_failure": "retrieval",
}

# Estimated minutes to recover, by dominant category (operator estimate, not a promise).
TTR_BY_CATEGORY = {
    "infra": 10, "model": 15, "retrieval": 15, "tool_call": 20,
    "prompt": 10, "context": 5, "network": 20, "auth": 10, "unknown": 30,
}

ENS_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+\.eth$", re.IGNORECASE)

# --- roster & continuity -----------------------------------------------------
# Doctrine: the position is never vacant. A dead/crash_loop (any TREATMENT_REQUIRED)
# starter ALWAYS triggers activation, every tier, 24/7. Tier only sets paging loudness.
BACKUP_PRIORITY = ["backup", "second_string", "specialist", "rotational"]
DEFAULT_CONDITIONING_MAX_AGE_DAYS = 30  # a backup that isn't recently tested is not a backup

# Locked doctrine (Mr D): a continuity event MUST resolve to exactly one of these three.
OUT_BACKUP = "BACKUP_RESTRICTED_DUTY"
OUT_HUMAN = "HUMAN_FAILOVER_SAFE_MODE"
OUT_SUSPEND = "OPERATIONS_SUSPENDED"

# Criticality controls paging URGENCY only — never whether an event is opened.
TIER_URGENCY = {
    "critical": "immediate_page",
    "material": "urgent_notification",
    "low_risk": "log_and_queue_owner_notice",
}
URGENCY_ORDER = ["none", "log_and_queue_owner_notice", "urgent_notification", "immediate_page"]
SUSPEND_PAGE_FLOOR = "urgent_notification"  # owner ruling: a SUSPENDED production lane must page
# Positions explicitly tagged as one of these may LOG instead of page when suspended.
NON_PRODUCTION_ENVS = {"sandbox", "test", "non_production", "dev", "staging"}


def _at_least(urgency, floor):
    return urgency if URGENCY_ORDER.index(urgency) >= URGENCY_ORDER.index(floor) else floor


# ----------------------------------------------------------------------------- helpers
def load_flight_sheet(path):
    with open(path, "r") as fh:
        sheet = yaml.safe_load(fh)
    for key in ("agent", "thresholds", "weights", "observations"):
        if key not in sheet:
            sys.exit(f"flight sheet missing required block: '{key}'")
    return sheet


def safe_div(num, den):
    den = den or 0
    return (num or 0) / den if den else 0.0


def is_ens(name):
    return bool(name and ENS_RE.match(str(name)))


def finding(severity, category, message):
    return {"severity": severity, "category": category, "message": message}


# ----------------------------------------------------------------------------- real probe
def run_vitals_probe(spec):
    """One REAL vitals probe. spec = 'systemctl:<unit>' or 'docker:<name>'.

    Returns dict: {vitals_state, process_up, crash_count, source, command, raw}.
    Local only — no network. This is the single automated check in v1.
    """
    kind, _, target = spec.partition(":")
    kind = kind.strip().lower()
    target = target.strip()
    if not target:
        sys.exit(f"--probe needs a target, e.g. 'docker:{spec or 'NAME'}'")

    if kind == "systemctl":
        # NB: do NOT use --value with multiple -p; systemd does not preserve the order
        # you request. Parse KEY=value lines explicitly instead.
        cmd = ["systemctl", "show", target, "-p", "ActiveState", "-p", "SubState", "-p", "NRestarts"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        kv = dict(
            line.split("=", 1) for line in out.stdout.splitlines() if "=" in line
        )
        active = kv.get("ActiveState", "").strip()
        sub = kv.get("SubState", "").strip()
        restarts = int(kv["NRestarts"]) if kv.get("NRestarts", "").strip().isdigit() else 0
        if active == "active":
            state = "alive"
        elif sub in ("auto-restart", "start") or (active == "activating" and restarts > 0):
            state = "crash_loop"
        elif active in ("failed", "inactive"):
            state = "dead"
        else:
            state = "unreachable"
        return {
            "vitals_state": state, "process_up": active == "active",
            "crash_count": restarts, "source": "systemctl",
            "command": " ".join(cmd),
            "raw": f"ActiveState={active} SubState={sub} NRestarts={restarts}",
        }

    if kind == "docker":
        cmd = ["docker", "inspect", "-f",
               "{{.State.Status}}|{{.State.Running}}|{{.RestartCount}}", target]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return {
                "vitals_state": "dead", "process_up": False, "crash_count": 0,
                "source": "docker", "command": " ".join(cmd),
                "raw": (out.stderr or "container not found").strip(),
            }
        status, running, restarts = (out.stdout.strip().split("|") + ["", "", "0"])[:3]
        restarts = int(restarts) if restarts.isdigit() else 0
        if status == "running":
            state = "alive"
        elif status == "restarting":
            state = "crash_loop"
        else:
            state = "dead"
        return {
            "vitals_state": state, "process_up": running.lower() == "true",
            "crash_count": restarts, "source": "docker", "command": " ".join(cmd),
            "raw": f"Status={status} Running={running} RestartCount={restarts}",
        }

    sys.exit(f"--probe kind must be 'systemctl' or 'docker', got '{kind}'")


# ----------------------------------------------------------------------------- health math
def compute_metrics(obs):
    gpu = obs.get("gpu", {}) or {}
    ctx = obs.get("context", {}) or {}
    return {
        "heartbeat_success_rate": safe_div(obs.get("successful_heartbeats"), obs.get("total_heartbeats")),
        "error_rate": safe_div(obs.get("errors"), obs.get("total_checks")),
        "successful_probe_count": int(obs.get("successful_probes", 0) or 0),
        "consecutive_failures": int(obs.get("consecutive_failures", 0) or 0),
        "latency_ms": float(obs.get("latency_ms", 0) or 0),
        "gpu_memory_used_pct": safe_div(gpu.get("used_vram_mb"), gpu.get("total_vram_mb")),
        "context_tokens_pct": safe_div(ctx.get("used_context_tokens"), ctx.get("max_context_tokens")),
    }


def category_health(obs, metrics, thr):
    vitals = 1.0
    if obs.get("vitals_state") != "alive" or not obs.get("process_up", False):
        vitals = 0.0
    if int(obs.get("crash_count", 0) or 0) > thr["max_crash_count"]:
        vitals = 0.0
    if metrics["consecutive_failures"] > thr["max_consecutive_failures"]:
        vitals = min(vitals, 0.0)

    pulse = metrics["heartbeat_success_rate"]
    if metrics["successful_probe_count"] < thr["min_successful_probe_count"]:
        pulse = min(pulse, 0.3)
    if metrics["latency_ms"] > thr["max_latency_ms"]:
        pulse -= 0.3
    pulse = max(0.0, min(1.0, pulse))

    flags = [f for f in (obs.get("bloodwork_flags") or []) if f]
    blood = 1.0 - 0.4 * len(flags)
    if metrics["error_rate"] > thr["max_error_rate"]:
        blood -= 0.4
    if metrics["gpu_memory_used_pct"] > thr["max_gpu_memory_used_pct"]:
        blood -= 0.2
    if metrics["context_tokens_pct"] > thr["max_context_tokens_pct"]:
        blood -= 0.2
    blood = max(0.0, min(1.0, blood))

    n = obs.get("neuro", {}) or {}
    neuro = 1.0
    if n.get("loaded_model") != n.get("expected_model"):
        neuro -= 0.4
    if n.get("loaded_adapter") != n.get("expected_adapter"):
        neuro -= 0.3
    if not n.get("sampling_sane", True):
        neuro -= 0.2
    if not n.get("system_prompt_ok", True):
        neuro -= 0.3
    neuro = max(0.0, min(1.0, neuro))

    history = 1.0 if not (obs.get("recent_changes") or []) else 0.7
    return {"vitals": vitals, "pulse": pulse, "bloodwork": blood, "neuro": neuro, "history": history}


def stability_score(cat, weights):
    total_w = sum(weights.values()) or 1.0
    return round(sum(cat[k] * weights.get(k, 0.0) for k in cat) / total_w * 100, 1)


# ----------------------------------------------------------------------------- findings
def collect_findings(obs, metrics, thr):
    """Build the explicit HARD_FAULT / SOFT_WARNING list with root_cause_category."""
    f = []
    vs = obs.get("vitals_state")
    if vs in HARD_VITALS:
        cat = "network" if vs == "unreachable" else "infra"
        f.append(finding(HARD_FAULT, cat, f"vitals: agent is {vs}"))
    if not obs.get("process_up", False) and vs == "alive":
        f.append(finding(HARD_FAULT, "infra", "vitals: process_up false despite vitals_state=alive"))
    if int(obs.get("crash_count", 0) or 0) > thr["max_crash_count"]:
        f.append(finding(HARD_FAULT, "infra", f"vitals: crash_count {obs.get('crash_count')} > max {thr['max_crash_count']}"))
    if metrics["consecutive_failures"] > thr["max_consecutive_failures"]:
        f.append(finding(HARD_FAULT, "infra", f"pulse: consecutive_failures {metrics['consecutive_failures']} > max {thr['max_consecutive_failures']}"))
    if metrics["successful_probe_count"] < thr["min_successful_probe_count"]:
        f.append(finding(HARD_FAULT, "infra", f"pulse: successful_probe_count {metrics['successful_probe_count']} < min {thr['min_successful_probe_count']}"))
    if metrics["heartbeat_success_rate"] < thr["min_heartbeat_success_rate"]:
        f.append(finding(HARD_FAULT, "infra", f"pulse: heartbeat_success_rate {metrics['heartbeat_success_rate']:.2f} < min {thr['min_heartbeat_success_rate']}"))
    if metrics["error_rate"] > thr["max_error_rate"]:
        f.append(finding(HARD_FAULT, "infra", f"bloodwork: error_rate {metrics['error_rate']:.2f} > max {thr['max_error_rate']}"))

    for flag in [x for x in (obs.get("bloodwork_flags") or []) if x]:
        if flag in BLOODWORK_CATEGORY:
            f.append(finding(HARD_FAULT, BLOODWORK_CATEGORY[flag], f"bloodwork: {flag}"))
        else:
            f.append(finding(SOFT_WARNING, "unknown", f"bloodwork: unrecognized flag '{flag}'"))

    n = obs.get("neuro", {}) or {}
    if n.get("loaded_model") != n.get("expected_model"):
        f.append(finding(HARD_FAULT, "model", f"neuro: model mismatch: loaded '{n.get('loaded_model')}' != expected '{n.get('expected_model')}'"))
    if n.get("loaded_adapter") != n.get("expected_adapter"):
        f.append(finding(HARD_FAULT, "model", f"neuro: adapter mismatch: loaded '{n.get('loaded_adapter')}' != expected '{n.get('expected_adapter')}'"))
    if not n.get("sampling_sane", True):
        f.append(finding(HARD_FAULT, "prompt", "neuro: sampling params not sane"))
    if not n.get("system_prompt_ok", True):
        f.append(finding(HARD_FAULT, "prompt", "neuro: system prompt missing/garbled"))

    if metrics["latency_ms"] > thr["max_latency_ms"]:
        f.append(finding(SOFT_WARNING, "infra", f"pulse: latency_ms {metrics['latency_ms']:.0f} > max {thr['max_latency_ms']}"))
    if metrics["gpu_memory_used_pct"] > thr["max_gpu_memory_used_pct"]:
        f.append(finding(SOFT_WARNING, "infra", f"bloodwork: gpu_memory_used_pct {metrics['gpu_memory_used_pct']:.2f} > max {thr['max_gpu_memory_used_pct']}"))
    if metrics["context_tokens_pct"] > thr["max_context_tokens_pct"]:
        f.append(finding(SOFT_WARNING, "context", f"bloodwork: context_tokens_pct {metrics['context_tokens_pct']:.2f} > max {thr['max_context_tokens_pct']}"))
    return f


def dominant_category(findings, severity):
    cats = {x["category"] for x in findings if x["severity"] == severity}
    for c in CATEGORY_PRIORITY:
        if c in cats:
            return c
    return None


def diagnosis_confidence(findings, obs, hard, dominant):
    """0.0-1.0 certainty in the diagnosis. Explainable, deterministic."""
    if not findings:
        return 0.95  # confidently healthy
    if not hard:
        return 0.60  # soft-only: degraded but cause not pinned
    distinct = {x["category"] for x in hard}
    conf = 0.55
    if len(distinct) == 1:
        conf += 0.25
    if obs.get("recent_changes"):
        conf += 0.10
    if obs.get("last_known_good"):
        conf += 0.05
    if dominant == "unknown":
        conf -= 0.25
    if len(distinct) >= 3:
        conf -= 0.10
    return round(max(0.10, min(0.97, conf)), 2)


def needs_human(discharge, confidence, hard, dominant):
    if discharge == "DISCHARGE_TO_EVAL_CURATOR":
        return False
    distinct = {x["category"] for x in hard}
    return bool(
        confidence < 0.60
        or dominant in {"unknown", "network", "auth"}
        or len(distinct) >= 3
    )


def time_to_recovery(discharge, dominant, human):
    if discharge == "DISCHARGE_TO_EVAL_CURATOR":
        return 0
    if discharge == "OBSERVE":
        return 5
    ttr = TTR_BY_CATEGORY.get(dominant, 30)
    if human:
        ttr += 15
    return ttr


def decide(hard, soft):
    if hard:
        return "TREATMENT_REQUIRED", False
    if soft:
        return "OBSERVE", False
    return "DISCHARGE_TO_EVAL_CURATOR", True


def pulse_status(obs, metrics, thr):
    if obs.get("vitals_state") in {"dead", "crash_loop", "unreachable"}:
        return "flatline"
    if metrics["successful_probe_count"] == 0 or metrics["heartbeat_success_rate"] == 0:
        return "flatline"
    if metrics["heartbeat_success_rate"] < thr["min_heartbeat_success_rate"] or metrics["latency_ms"] > thr["max_latency_ms"]:
        return "degraded"
    return "ok"


def build_diagnosis(hard, soft):
    if not hard and not soft:
        return "Agent healthy across vitals, pulse, bloodwork, and neuro. Stable."
    if hard:
        return "Hard fault present: " + hard[0]["message"]
    return "Alive but degraded: " + soft[0]["message"]


def build_treatment(hard, soft, obs):
    tx = []
    joined = " ".join(x["message"] for x in hard + soft).lower()
    vs = obs.get("vitals_state")
    if vs == "dead":
        tx.append("Restart the service and confirm it stays up.")
    if vs == "crash_loop":
        tx.append("Stop the restart loop; inspect crash logs; roll back last change.")
    if vs == "unreachable":
        tx.append("Check ingress/port/network path between caller and agent.")
    if vs == "hung":
        tx.append("Kill and restart the hung worker; check for deadlock / stuck request.")
    if "oom" in joined or "gpu_memory" in joined:
        tx.append("Reduce batch size or max_context_tokens; free VRAM; restart.")
    if "context" in joined and "blowout" in joined:
        tx.append("Truncate/limit context; lower max_context_tokens.")
    if "model mismatch" in joined:
        tx.append("Reload the correct model weights, then re-run the Doctor.")
    if "adapter mismatch" in joined:
        tx.append("Load the expected adapter revision, then re-run the Doctor.")
    if "system prompt" in joined:
        tx.append("Restore the correct system prompt / repair the chat template.")
    if "sampling" in joined:
        tx.append("Reset sampling params (temp/top_p/max_tokens) to known-good values.")
    if "template_corruption" in joined:
        tx.append("Repair the chat template formatting.")
    if "tool_call_failure" in joined:
        tx.append("Check tool/function definitions and downstream tool availability.")
    if "retrieval_failure" in joined:
        tx.append("Check the retrieval backend/index and connectivity.")
    if "auth_error" in joined:
        tx.append("Rotate/restore the API key or credential; verify auth config.")
    if not hard and soft:
        tx.append("No hard fault. Observe under load before promoting; recheck shortly.")
    if not tx:
        tx.append("No treatment needed. Stable.")
    return tx


def sha256_receipt(receipt):
    """Hash everything except the hash field itself, canonical + sorted."""
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ----------------------------------------------------------------------------- roster & continuity
def load_depth_chart(path):
    with open(path, "r") as fh:
        dc = yaml.safe_load(fh)
    for key in ("position_group", "roster"):
        if key not in dc:
            sys.exit(f"depth chart missing required block: '{key}'")
    return dc


def validate_depth_chart(path):
    """Structural + semantic validator for a depth chart. Prints errors/warnings and
    returns an exit code. Enforces the doctrine: exactly one starter; backups must carry
    an approved play set (no untested authority); flags benched/stale/safe-mode gaps."""
    valid_tiers = set(TIER_URGENCY)
    valid_roles = {"starter", "backup", "second_string", "specialist", "rotational"}
    errors, warns = [], []
    try:
        dc = load_depth_chart(path)
    except SystemExit as e:
        print(f"  [ERROR] {e}")
        return 1

    tier = dc.get("criticality_tier")
    if tier and tier not in valid_tiers:
        errors.append(f"criticality_tier '{tier}' not in {sorted(valid_tiers)}")
    roster = dc.get("roster", [])
    starters = [m for m in roster if m.get("depth_chart") == "starter"]
    if len(starters) != 1:
        errors.append(f"expected exactly 1 starter, found {len(starters)}")
    max_age = dc.get("conditioning_max_age_days", DEFAULT_CONDITIONING_MAX_AGE_DAYS)
    eligible_backups = 0
    for m in roster:
        role = m.get("depth_chart")
        if role not in valid_roles:
            errors.append(f"{m.get('agent_id')}: invalid depth_chart role '{role}'")
        if not m.get("agent_id"):
            errors.append("a roster member is missing agent_id")
        if role and role != "starter":
            if not (m.get("permissions", {}) or {}).get("may"):
                warns.append(f"{m.get('agent_id')}: no approved play set (permissions.may) — INELIGIBLE (untested authority)")
            elif _backup_eligible(m, max_age):
                eligible_backups += 1
            else:
                warns.append(f"{m.get('agent_id')}: benched or stale — not an eligible backup")
    has_human = bool(dc.get("human_failover_owner") or dc.get("human_coach"))
    safe = dc.get("safe_mode_available", True)
    if eligible_backups == 0 and not (has_human and safe):
        warns.append("no eligible backup AND no safe human coverage → a starter failure here will OPERATIONS_SUSPENDED")

    for e in errors:
        print(f"  [ERROR] {e}")
    for w in warns:
        print(f"  [warn ] {w}")
    ok = not errors
    print(f"VALIDATE {os.path.basename(path)}: {'OK' if ok else 'INVALID'}  "
          f"(eligible backups: {eligible_backups})")
    return 0 if ok else 1


def _backup_eligible(member, max_age_days):
    """A backup is eligible only if it is (a) not benched, (b) not stale on conditioning, and
    (c) has an APPROVED reduced-permission play set. Doctrine: never grant untested authority —
    a backup with no approved `permissions.may` cannot be activated."""
    if member.get("eligible") is False:
        return False
    if not (member.get("permissions", {}) or {}).get("may"):
        return False  # no approved play set -> activating it would be untested authority
    lkg = member.get("last_conditioning")
    if lkg and max_age_days:
        try:
            d = datetime.date.fromisoformat(str(lkg)[:10])
            if (datetime.date.today() - d).days > int(max_age_days):
                return False
        except ValueError:
            pass
    return True


def pick_backup(dc):
    """Choose the highest-priority eligible non-starter to cover the position."""
    max_age = dc.get("conditioning_max_age_days", DEFAULT_CONDITIONING_MAX_AGE_DAYS)
    candidates = [m for m in dc.get("roster", []) if m.get("depth_chart") != "starter"]
    eligible = [m for m in candidates if _backup_eligible(m, max_age)]
    eligible.sort(key=lambda m: BACKUP_PRIORITY.index(m["depth_chart"])
                  if m.get("depth_chart") in BACKUP_PRIORITY else 99)
    return eligible[0] if eligible else None


def build_continuity_action(receipt, dc):
    """Next-man-up (locked doctrine).
      1. A dead/crash_loop (any TREATMENT_REQUIRED) starter ALWAYS opens a continuity event.
      2. The position is never silently vacant.
      3. Activation never grants untested authority — only a backup's own approved play set.
      The event resolves to exactly one outcome:
        - BACKUP_RESTRICTED_DUTY    (eligible pre-evaluated backup; its reduced play set only)
        - HUMAN_FAILOVER_SAFE_MODE  (no backup; lane-defined safe-mode behavior only)
        - OPERATIONS_SUSPENDED      (neither can proceed safely; preserve receipts + escalate)
      Criticality controls paging urgency, never whether an event is opened."""
    discharge = receipt["discharge_status"]
    group = dc["position_group"]
    tier = dc.get("criticality_tier", "material")
    urgency = TIER_URGENCY.get(tier, "urgent_notification")
    env = str(dc.get("environment", "production")).lower()
    is_production = not (dc.get("non_production") or env in NON_PRODUCTION_ENVS)
    human_owner = dc.get("human_failover_owner") or dc.get("human_coach")
    human_available = dc.get("human_failover_available", bool(human_owner))
    safe_mode = dc.get("safe_mode_available", True)  # can the lane run in a reduced safe mode?
    starter = next((m["agent_id"] for m in dc.get("roster", []) if m.get("depth_chart") == "starter"),
                   receipt["agent_id"])

    base = {"position_group": group, "criticality_tier": tier, "environment": env,
            "starter": starter, "human_owner": human_owner}

    if discharge == "DISCHARGE_TO_EVAL_CURATOR":
        return {**base, "triggered": False, "trigger_reason": None, "starter_status": "ACTIVE",
                "outcome": "NO_CONTINUITY_EVENT", "workflow_status": "NORMAL", "activated": None,
                "activated_permissions": [], "requires_human_approval": [],
                "human_owner_notified": False, "escalation_urgency": "none", "limitations": []}

    if discharge == "OBSERVE":
        return {**base, "triggered": False, "trigger_reason": "degraded — watch under load",
                "starter_status": "OBSERVE", "outcome": "MONITOR", "workflow_status": "DEGRADED_MONITORED",
                "activated": None, "activated_permissions": [], "requires_human_approval": [],
                "human_owner_notified": tier == "critical",
                "escalation_urgency": "urgent_notification" if tier == "critical" else "log_and_queue_owner_notice",
                "limitations": ["starter remains on the field; monitor before promoting"]}

    # --- continuity event opened: starter comes off the field, ALWAYS. Resolve to one outcome. ---
    reason = receipt["hard_faults"][0] if receipt.get("hard_faults") else "treatment required"
    backup = pick_backup(dc)

    if backup:  # BACKUP_RESTRICTED_DUTY — activate ONLY the backup's approved reduced play set
        perms = backup.get("permissions", {}) or {}
        may = perms.get("may", []) or []
        gated = perms.get("may_not_without_human_approval", []) or []
        limits = [f"activated play set (backup-approved only): {', '.join(may)}"]
        limits += [f"human approval required: {a}" for a in gated]
        limits.append(f"coverage by {backup.get('depth_chart')} agent — restricted duty, never starter authority")
        return {**base, "triggered": True, "trigger_reason": reason, "starter_status": "INJURED_RESERVE",
                "outcome": OUT_BACKUP, "workflow_status": "COVERED_BY_BACKUP", "activated": backup["agent_id"],
                "activated_permissions": may, "requires_human_approval": gated,
                "human_owner_notified": True, "escalation_urgency": urgency, "limitations": limits}

    if human_owner and human_available and safe_mode:  # HUMAN_FAILOVER_SAFE_MODE — lane safe-mode only
        return {**base, "triggered": True, "trigger_reason": reason, "starter_status": "INJURED_RESERVE",
                "outcome": OUT_HUMAN, "workflow_status": "COVERED_BY_HUMAN_SAFE_MODE", "activated": None,
                "activated_permissions": [], "requires_human_approval": ["all lane actions"],
                "human_owner_notified": True, "escalation_urgency": urgency,
                "limitations": ["no eligible backup — lane runs in safe mode only (draft / read-only / queue-and-hold)",
                                f"human owner ({human_owner}) covers / authorizes until a backup is cleared"]}

    # OPERATIONS_SUSPENDED — fail-closed: neither backup nor safe human coverage can proceed.
    why = []
    if not (human_owner and human_available):
        why.append("no available human failover owner")
    if not safe_mode:
        why.append("lane has no safe degraded mode (actions are not reversible / holdable)")
    # Owner ruling: a SUSPENDED production lane pages at minimum severity, regardless of tier.
    # Exemption: explicitly tagged sandbox/test/non-production lanes may log instead.
    suspend_urgency = _at_least(urgency, SUSPEND_PAGE_FLOOR) if is_production else urgency
    floor_note = ("production suspension — paged at minimum severity per owner ruling"
                  if is_production else f"non-production ({env}) — exempt from the suspension paging floor; logged")
    return {**base, "triggered": True, "trigger_reason": reason, "starter_status": "INJURED_RESERVE",
            "outcome": OUT_SUSPEND, "workflow_status": "SUSPENDED", "activated": None,
            "activated_permissions": [], "requires_human_approval": ["all lane actions (suspended)"],
            "human_owner_notified": True, "escalation_urgency": suspend_urgency, "receipts_preserved": True,
            "limitations": ["OPERATIONS SUSPENDED — all agent actions blocked pending human control",
                            "reason: " + "; ".join(why),
                            floor_note,
                            "receipts preserved; no work proceeds until a human assumes control or a backup is cleared"]}


# ----------------------------------------------------------------------------- main visit
def run_visit(sheet, probe_spec=None, depth_chart=None):
    agent = sheet["agent"]
    thr = sheet["thresholds"]
    weights = sheet["weights"]
    obs = dict(sheet["observations"])

    vitals_probe = None
    if probe_spec is None:
        probe_spec = agent.get("probe")  # optional, from the sheet
    if probe_spec:
        vitals_probe = run_vitals_probe(probe_spec)
        obs["vitals_state"] = vitals_probe["vitals_state"]
        obs["process_up"] = vitals_probe["process_up"]
        obs["crash_count"] = vitals_probe["crash_count"]

    metrics = compute_metrics(obs)
    cat = category_health(obs, metrics, thr)
    metrics["stability_score"] = stability_score(cat, weights)

    findings = collect_findings(obs, metrics, thr)
    hard = [x for x in findings if x["severity"] == HARD_FAULT]
    soft = [x for x in findings if x["severity"] == SOFT_WARNING]
    discharge, ready = decide(hard, soft)

    dom = dominant_category(findings, HARD_FAULT) or dominant_category(findings, SOFT_WARNING)
    if discharge == "DISCHARGE_TO_EVAL_CURATOR":
        root_cause = "none"
    else:
        root_cause = dom or "unknown"

    confidence = diagnosis_confidence(findings, obs, hard, dom)
    human = needs_human(discharge, confidence, hard, dom)
    ttr = time_to_recovery(discharge, dom, human)

    agent_id = agent.get("agent_id")
    agent_ens = agent.get("agent_ens") or (agent_id if is_ens(agent_id) else None)

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "offline_mode": bool(sheet.get("mode", {}).get("offline", True)),
        "offline_note": "Local triage only. Source data never leaves the office.",
        "agent_id": agent_id,
        "agent_ens": agent_ens,
        "agent_name": agent.get("agent_name"),
        "host": agent.get("host"),
        "symptom": agent.get("symptom"),
        "vitals_status": obs.get("vitals_state"),
        "vitals_probe": vitals_probe,  # null unless a real probe ran
        "pulse_status": pulse_status(obs, metrics, thr),
        "bloodwork_findings": [x for x in (obs.get("bloodwork_flags") or []) if x],
        "neuro_findings": [x["message"].replace("neuro: ", "") for x in hard if x["category"] in ("model", "prompt")],
        "recent_changes": obs.get("recent_changes") or [],
        "last_known_good": agent.get("last_known_good"),
        "metrics": metrics,
        "findings": findings,
        "hard_faults": [x["message"] for x in hard],
        "soft_warnings": [x["message"] for x in soft],
        "root_cause_category": root_cause,
        "diagnosis": build_diagnosis(hard, soft),
        "diagnosis_confidence": confidence,
        "treatment_plan": build_treatment(hard, soft, obs),
        "time_to_recovery_minutes": ttr,
        "human_required": human,
        "discharge_status": discharge,
        "ready_for_eval_curator": ready,
        "continuity_action": None,  # filled below when a depth chart is supplied
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if depth_chart:
        receipt["continuity_action"] = build_continuity_action(receipt, depth_chart)
    receipt["receipt_sha256"] = sha256_receipt(receipt)
    return receipt


def resolve_depth_chart(sheet, sheet_path, explicit=None):
    """Explicit --depth-chart wins; otherwise a sheet-level `depth_chart:` path (relative
    to the sheet) is loaded. Returns the depth chart dict or None."""
    if explicit:
        return load_depth_chart(explicit)
    rel = sheet.get("depth_chart")
    if rel:
        base = os.path.dirname(os.path.abspath(sheet_path))
        return load_depth_chart(os.path.join(base, rel))
    return None


def selftest(examples_dir):
    """Run every *.yaml in examples_dir and assert expected discharge from its filename
    convention or an embedded `expect:` key. If a sheet declares `depth_chart:` and
    `expect_outcome:`, the continuity outcome is asserted too. Returns exit code."""
    expect_map = {
        "healthy": "DISCHARGE_TO_EVAL_CURATOR",
        "dead": "TREATMENT_REQUIRED", "crash": "TREATMENT_REQUIRED",
        "hung": "TREATMENT_REQUIRED", "garbage": "TREATMENT_REQUIRED",
        "mismatch": "TREATMENT_REQUIRED", "observe": "OBSERVE",
    }
    sheets = sorted(f for f in os.listdir(examples_dir) if f.endswith(".yaml"))
    if not sheets:
        print(f"no .yaml sheets in {examples_dir}")
        return 1
    ok = True
    for name in sheets:
        path = os.path.join(examples_dir, name)
        sheet = load_flight_sheet(path)
        expected = sheet.get("expect")
        if not expected:
            key = next((k for k in expect_map if k in name), None)
            expected = expect_map.get(key)
        dc = resolve_depth_chart(sheet, path)
        r = run_visit(sheet, depth_chart=dc)
        got = r["discharge_status"]
        passed = (expected is None) or (got == expected)
        extra = ""
        ca = r.get("continuity_action") or {}
        exp_out = sheet.get("expect_outcome")
        if exp_out:
            got_out = ca.get("outcome")
            passed = passed and (got_out == exp_out)
            extra += f"  outcome={got_out} (expect {exp_out})"
        exp_urg = sheet.get("expect_urgency")
        if exp_urg:
            got_urg = ca.get("escalation_urgency")
            passed = passed and (got_urg == exp_urg)
            extra += f"  urgency={got_urg} (expect {exp_urg})"
        ok = ok and passed
        flag = "ok " if passed else "FAIL"
        print(f"  [{flag}] {name:24s} got={got:26s} expect={expected}{extra}")
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def print_summary(r, out_path):
    line = "=" * 68
    print(line)
    idline = r["agent_id"] + (f"  (ENS: {r['agent_ens']})" if r.get("agent_ens") and r["agent_ens"] != r["agent_id"] else "")
    print(f"  SWARM-DOCTOR — {r['agent_name']} [{idline}] @ {r['host']}")
    print(f"  offline_mode={r['offline_mode']}   (source data never leaves the office)")
    print(line)
    print(f"  Symptom    : {r['symptom']}")
    print(f"  Vitals     : {r['vitals_status']}" + (f"   (probe: {r['vitals_probe']['source']} — {r['vitals_probe']['raw']})" if r.get("vitals_probe") else ""))
    print(f"  Pulse      : {r['pulse_status']}")
    m = r["metrics"]
    print(f"  Heartbeat  : {m['heartbeat_success_rate']:.2f}   Error: {m['error_rate']:.2f}   Probes ok: {m['successful_probe_count']}")
    print(f"  Latency    : {m['latency_ms']:.0f} ms   GPU: {m['gpu_memory_used_pct']:.0%}   Context: {m['context_tokens_pct']:.0%}")
    print(f"  Stability  : {m['stability_score']} / 100")
    if r["last_known_good"]:
        print(f"  Last good  : {r['last_known_good']}")
    if r["hard_faults"]:
        print("  HARD FAULTS:")
        for x in r["hard_faults"]:
            print(f"    - {x}")
    if r["soft_warnings"]:
        print("  SOFT WARNINGS:")
        for x in r["soft_warnings"]:
            print(f"    - {x}")
    print(f"  Root cause : {r['root_cause_category']}")
    print(f"  Dx         : {r['diagnosis']}  (confidence {r['diagnosis_confidence']})")
    print("  Tx         :")
    for t in r["treatment_plan"]:
        print(f"    - {t}")
    print(f"  ETR        : ~{r['time_to_recovery_minutes']} min   human_required={r['human_required']}")
    ca = r.get("continuity_action")
    if ca:
        print(line)
        print(f"  CONTINUITY : {ca['position_group']} (tier {ca['criticality_tier']})  starter={ca['starter_status']}")
        if ca["triggered"]:
            print(f"    outcome  : {ca['outcome']}")
            print(f"    workflow : {ca['workflow_status']}")
            print(f"    activated: {ca['activated'] or '— none —'}")
            print(f"    escalate : {ca['escalation_urgency']}  →  owner {ca['human_owner']} (notified={ca['human_owner_notified']})")
            for lim in ca["limitations"]:
                print(f"    limit    : {lim}")
        else:
            print(f"    outcome  : {ca['outcome']} (workflow {ca['workflow_status']})")
    print(line)
    print(f"  DISCHARGE  : {r['discharge_status']}   ready_for_eval_curator={r['ready_for_eval_curator']}")
    print(f"  sha256     : {r['receipt_sha256']}")
    print(f"  Receipt    : {out_path}")
    print(line)


def main():
    ap = argparse.ArgumentParser(description="Swarm-Doctor referee runner (v1).")
    ap.add_argument("--flight-sheet", help="path to flight_sheet.yaml")
    ap.add_argument("--out", help="path to write the JSON receipt")
    ap.add_argument("--probe", help="run one real vitals probe: 'systemctl:<unit>' or 'docker:<name>'")
    ap.add_argument("--depth-chart", help="path to a depth_chart.yaml for next-man-up continuity")
    ap.add_argument("--validate-depth-chart", metavar="PATH", help="validate a depth chart and exit")
    ap.add_argument("--selftest", metavar="DIR", help="run every .yaml sheet in DIR and assert discharge")
    ap.add_argument("--quiet", action="store_true", help="suppress the human summary")
    args = ap.parse_args()

    if args.validate_depth_chart:
        sys.exit(validate_depth_chart(args.validate_depth_chart))
    if args.selftest:
        sys.exit(selftest(args.selftest))
    if not args.flight_sheet:
        ap.error("--flight-sheet is required (or use --selftest DIR)")

    sheet = load_flight_sheet(args.flight_sheet)
    depth_chart = resolve_depth_chart(sheet, args.flight_sheet, args.depth_chart)
    receipt = run_visit(sheet, probe_spec=args.probe, depth_chart=depth_chart)

    out_path = args.out
    if not out_path:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rec_dir = os.path.join(here, "receipts")
        os.makedirs(rec_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        out_path = os.path.join(rec_dir, f"receipt_{receipt['agent_id']}_{stamp}.json")
    with open(out_path, "w") as fh:
        json.dump(receipt, fh, indent=2)

    if not args.quiet:
        print_summary(receipt, out_path)
    sys.exit({"DISCHARGE_TO_EVAL_CURATOR": 0, "OBSERVE": 1, "TREATMENT_REQUIRED": 2}[receipt["discharge_status"]])


if __name__ == "__main__":
    main()
