#!/usr/bin/env python3
"""
Swarm-Doctor referee runner.

Doctor before manager: triage a sick AI agent's HEALTH (not its answer quality),
then decide whether it gets treatment, observation, or discharge to eval-curator.

Usage:
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml
    python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --out receipts/visit.json

The flight sheet is machine-readable instructions: it carries the numeric thresholds,
the stability-score weights, and the `observations` block for this visit. This runner
loads it, computes health metrics, applies pass/fail thresholds, prints a human summary,
and writes a JSON receipt ending in one of:

    TREATMENT_REQUIRED | OBSERVE | DISCHARGE_TO_EVAL_CURATOR

It does NOT grade answer quality. That is eval-curator's job, only after discharge.

TODO(automation): the `observations` block is filled by hand today. Future work wires
real probes here (systemctl/docker/pm2 for vitals, an HTTP probe for pulse, log scraping
for bloodwork, a model-introspection call for neuro). The math + decision logic below
stays the same once observations are populated automatically.
"""

import argparse
import datetime
import json
import os
import sys

try:
    import yaml
except ImportError:
    sys.exit("Swarm-Doctor needs PyYAML. Install with: pip install pyyaml")

SCHEMA_VERSION = "1.0"
HARD_VITALS = {"dead", "crash_loop", "unreachable", "hung"}
CRITICAL_BLOODWORK = {
    "oom",
    "cuda_error",
    "context_blowout",
    "template_corruption",
    "tool_call_failure",
}


def load_flight_sheet(path):
    with open(path, "r") as fh:
        sheet = yaml.safe_load(fh)
    for key in ("agent", "thresholds", "weights", "observations"):
        if key not in sheet:
            sys.exit(f"flight sheet missing required block: '{key}'")
    return sheet


def safe_div(num, den):
    """Divide, returning 0.0 on a zero/None denominator (no data == no credit)."""
    den = den or 0
    return (num or 0) / den if den else 0.0


def compute_metrics(obs):
    """Turn raw observations into the health math."""
    gpu = obs.get("gpu", {}) or {}
    ctx = obs.get("context", {}) or {}
    m = {
        "heartbeat_success_rate": safe_div(
            obs.get("successful_heartbeats"), obs.get("total_heartbeats")
        ),
        "error_rate": safe_div(obs.get("errors"), obs.get("total_checks")),
        "successful_probe_count": int(obs.get("successful_probes", 0) or 0),
        "consecutive_failures": int(obs.get("consecutive_failures", 0) or 0),
        "latency_ms": float(obs.get("latency_ms", 0) or 0),
        "gpu_memory_used_pct": safe_div(
            gpu.get("used_vram_mb"), gpu.get("total_vram_mb")
        ),
        "context_tokens_pct": safe_div(
            ctx.get("used_context_tokens"), ctx.get("max_context_tokens")
        ),
    }
    return m


def category_health(obs, metrics, thr):
    """Score each intake section 0.0-1.0 for the weighted stability_score."""
    # Vitals: binary on being alive + within crash/failure budgets.
    vitals = 1.0
    if obs.get("vitals_state") != "alive" or not obs.get("process_up", False):
        vitals = 0.0
    if int(obs.get("crash_count", 0) or 0) > thr["max_crash_count"]:
        vitals = 0.0
    if metrics["consecutive_failures"] > thr["max_consecutive_failures"]:
        vitals = min(vitals, 0.0)

    # Pulse: heartbeat rate, penalized for stale/slow responses and missing probes.
    pulse = metrics["heartbeat_success_rate"]
    if metrics["successful_probe_count"] < thr["min_successful_probe_count"]:
        pulse = min(pulse, 0.3)
    if metrics["latency_ms"] > thr["max_latency_ms"]:
        pulse -= 0.3
    pulse = max(0.0, min(1.0, pulse))

    # Bloodwork: start clean, subtract per critical flag, fail on error_rate breach.
    flags = [f for f in (obs.get("bloodwork_flags") or []) if f]
    blood = 1.0 - 0.4 * len(flags)
    if metrics["error_rate"] > thr["max_error_rate"]:
        blood -= 0.4
    if metrics["gpu_memory_used_pct"] > thr["max_gpu_memory_used_pct"]:
        blood -= 0.2
    if metrics["context_tokens_pct"] > thr["max_context_tokens_pct"]:
        blood -= 0.2
    blood = max(0.0, min(1.0, blood))

    # Neuro: model + adapter match, sane sampling, prompt present.
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

    # History: changes are a clue, not a fault. Recent change lowers confidence a touch.
    history = 1.0 if not (obs.get("recent_changes") or []) else 0.7

    return {
        "vitals": vitals,
        "pulse": pulse,
        "bloodwork": blood,
        "neuro": neuro,
        "history": history,
    }


def stability_score(cat, weights):
    total_w = sum(weights.values()) or 1.0
    score = sum(cat[k] * weights.get(k, 0.0) for k in cat) / total_w
    return round(score * 100, 1)


def evaluate(obs, metrics, thr):
    """Collect hard faults and soft warnings; these drive the discharge decision."""
    hard, soft = [], []

    vs = obs.get("vitals_state")
    if vs in HARD_VITALS:
        hard.append(f"vitals: agent is {vs}")
    if not obs.get("process_up", False) and vs == "alive":
        hard.append("vitals: process_up is false despite vitals_state=alive")
    if int(obs.get("crash_count", 0) or 0) > thr["max_crash_count"]:
        hard.append(
            f"vitals: crash_count {obs.get('crash_count')} > max {thr['max_crash_count']}"
        )
    if metrics["consecutive_failures"] > thr["max_consecutive_failures"]:
        hard.append(
            f"pulse: consecutive_failures {metrics['consecutive_failures']} "
            f"> max {thr['max_consecutive_failures']}"
        )
    if metrics["successful_probe_count"] < thr["min_successful_probe_count"]:
        hard.append(
            f"pulse: successful_probe_count {metrics['successful_probe_count']} "
            f"< min {thr['min_successful_probe_count']}"
        )
    if metrics["heartbeat_success_rate"] < thr["min_heartbeat_success_rate"]:
        hard.append(
            f"pulse: heartbeat_success_rate {metrics['heartbeat_success_rate']:.2f} "
            f"< min {thr['min_heartbeat_success_rate']}"
        )
    if metrics["error_rate"] > thr["max_error_rate"]:
        hard.append(
            f"bloodwork: error_rate {metrics['error_rate']:.2f} > max {thr['max_error_rate']}"
        )

    flags = [f for f in (obs.get("bloodwork_flags") or []) if f]
    for f in flags:
        if f in CRITICAL_BLOODWORK:
            hard.append(f"bloodwork: {f}")
        else:
            soft.append(f"bloodwork: unrecognized flag '{f}'")

    n = obs.get("neuro", {}) or {}
    neuro_findings = []
    if n.get("loaded_model") != n.get("expected_model"):
        msg = f"model mismatch: loaded '{n.get('loaded_model')}' != expected '{n.get('expected_model')}'"
        hard.append("neuro: " + msg)
        neuro_findings.append(msg)
    if n.get("loaded_adapter") != n.get("expected_adapter"):
        msg = f"adapter mismatch: loaded '{n.get('loaded_adapter')}' != expected '{n.get('expected_adapter')}'"
        hard.append("neuro: " + msg)
        neuro_findings.append(msg)
    if not n.get("sampling_sane", True):
        hard.append("neuro: sampling params not sane")
        neuro_findings.append("sampling params not sane")
    if not n.get("system_prompt_ok", True):
        hard.append("neuro: system prompt missing/garbled")
        neuro_findings.append("system prompt missing/garbled")

    # Soft warnings: alive but degraded / near the ceiling.
    if metrics["latency_ms"] > thr["max_latency_ms"]:
        soft.append(
            f"pulse: latency_ms {metrics['latency_ms']:.0f} > max {thr['max_latency_ms']}"
        )
    if metrics["gpu_memory_used_pct"] > thr["max_gpu_memory_used_pct"]:
        soft.append(
            f"bloodwork: gpu_memory_used_pct {metrics['gpu_memory_used_pct']:.2f} "
            f"> max {thr['max_gpu_memory_used_pct']}"
        )
    if metrics["context_tokens_pct"] > thr["max_context_tokens_pct"]:
        soft.append(
            f"bloodwork: context_tokens_pct {metrics['context_tokens_pct']:.2f} "
            f"> max {thr['max_context_tokens_pct']}"
        )

    return hard, soft, neuro_findings


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
    if (
        metrics["heartbeat_success_rate"] < thr["min_heartbeat_success_rate"]
        or metrics["latency_ms"] > thr["max_latency_ms"]
    ):
        return "degraded"
    return "ok"


def build_diagnosis(hard, soft, obs):
    if not hard and not soft:
        return "Agent healthy across vitals, pulse, bloodwork, and neuro. Stable."
    if hard:
        return "Hard fault present: " + hard[0]
    return "Alive but degraded: " + soft[0]


def build_treatment(hard, soft, obs):
    tx = []
    joined = " ".join(hard + soft).lower()
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
    if not hard and soft:
        tx.append("No hard fault. Observe under load before promoting; recheck shortly.")
    if not tx:
        tx.append("No treatment needed. Stable.")
    return tx


def main():
    ap = argparse.ArgumentParser(description="Swarm-Doctor referee runner.")
    ap.add_argument("--flight-sheet", required=True, help="path to flight_sheet.yaml")
    ap.add_argument("--out", help="path to write the JSON receipt")
    ap.add_argument("--quiet", action="store_true", help="suppress the human summary")
    args = ap.parse_args()

    sheet = load_flight_sheet(args.flight_sheet)
    agent = sheet["agent"]
    thr = sheet["thresholds"]
    weights = sheet["weights"]
    obs = sheet["observations"]

    metrics = compute_metrics(obs)
    cat = category_health(obs, metrics, thr)
    metrics["stability_score"] = stability_score(cat, weights)

    hard, soft, neuro_findings = evaluate(obs, metrics, thr)
    discharge, ready = decide(hard, soft)

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "agent_id": agent.get("agent_id"),
        "agent_name": agent.get("agent_name"),
        "host": agent.get("host"),
        "symptom": agent.get("symptom"),
        "vitals_status": obs.get("vitals_state"),
        "pulse_status": pulse_status(obs, metrics, thr),
        "bloodwork_findings": [f for f in (obs.get("bloodwork_flags") or []) if f],
        "neuro_findings": neuro_findings,
        "recent_changes": obs.get("recent_changes") or [],
        "metrics": metrics,
        "hard_faults": hard,
        "soft_warnings": soft,
        "diagnosis": build_diagnosis(hard, soft, obs),
        "treatment_plan": build_treatment(hard, soft, obs),
        "discharge_status": discharge,
        "ready_for_eval_curator": ready,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    out_path = args.out
    if not out_path:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rec_dir = os.path.join(here, "receipts")
        os.makedirs(rec_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        out_path = os.path.join(rec_dir, f"receipt_{agent.get('agent_id','agent')}_{stamp}.json")
    with open(out_path, "w") as fh:
        json.dump(receipt, fh, indent=2)

    if not args.quiet:
        print_summary(receipt, out_path)

    # Exit code mirrors the decision: 0 discharge, 1 observe, 2 treatment.
    sys.exit({"DISCHARGE_TO_EVAL_CURATOR": 0, "OBSERVE": 1, "TREATMENT_REQUIRED": 2}[discharge])


def print_summary(r, out_path):
    line = "=" * 64
    print(line)
    print(f"  SWARM-DOCTOR — {r['agent_name']} ({r['agent_id']}) @ {r['host']}")
    print(line)
    print(f"  Symptom    : {r['symptom']}")
    print(f"  Vitals     : {r['vitals_status']}")
    print(f"  Pulse      : {r['pulse_status']}")
    m = r["metrics"]
    print(f"  Heartbeat  : {m['heartbeat_success_rate']:.2f}   "
          f"Error rate : {m['error_rate']:.2f}   Probes ok: {m['successful_probe_count']}")
    print(f"  Latency    : {m['latency_ms']:.0f} ms   "
          f"GPU mem: {m['gpu_memory_used_pct']:.0%}   Context: {m['context_tokens_pct']:.0%}")
    print(f"  Stability  : {m['stability_score']} / 100")
    if r["bloodwork_findings"]:
        print(f"  Bloodwork  : {', '.join(r['bloodwork_findings'])}")
    if r["neuro_findings"]:
        print(f"  Neuro      : {'; '.join(r['neuro_findings'])}")
    if r["hard_faults"]:
        print("  HARD FAULTS:")
        for f in r["hard_faults"]:
            print(f"    - {f}")
    if r["soft_warnings"]:
        print("  Warnings   :")
        for f in r["soft_warnings"]:
            print(f"    - {f}")
    print(f"  Dx         : {r['diagnosis']}")
    print("  Tx         :")
    for t in r["treatment_plan"]:
        print(f"    - {t}")
    print(line)
    print(f"  DISCHARGE  : {r['discharge_status']}")
    print(f"  Ready for eval-curator: {r['ready_for_eval_curator']}")
    print(f"  Receipt    : {out_path}")
    print(line)


if __name__ == "__main__":
    main()
