# Swarm-Doctor — Doctrine

> **Doctor before manager.**
> Swarm-Doctor revives and stabilizes a sick AI agent *before* eval-curator grades it.

## The one idea (read this in 30 seconds)

`eval-curator` is the manager. It grades a **healthy** agent's answers against the
rubric. It assumes the patient is breathing.

A dead, hung, crash-looping, or confused agent is **not** a quality problem. It is a
**vitals** problem. You do not send a man in cardiac arrest to his performance review.

So the order is fixed:

```
Swarm-Doctor (triage → stabilize)  →  eval-curator (grade → train)
```

Health triage and performance evaluation are **separate jobs**. Swarm-Doctor never
grades answer quality. It only answers one question:

> **Is this agent healthy enough to be evaluated?**

## Scope (what the Doctor does and does not do)

| Swarm-Doctor DOES | Swarm-Doctor does NOT |
|---|---|
| Check if the process is alive | Score answer accuracy |
| Measure pulse (latency, heartbeat, probes) | Apply the eval-curator rubric |
| Read bloodwork (logs, OOM, CUDA, errors) | Decide Royal Jelly tiers |
| Verify neuro (right model/adapter/prompt) | Train or fine-tune anything |
| Note recent changes (history) | Judge CRE judgment or format |
| Diagnose, treat, then discharge | Touch a patient that is already healthy and graded |

## Intake (the shrink's chart)

The Doctor works through six sections, in order, every time:

1. **Vitals** — alive, dead, crash-looping, hung, or unreachable?
2. **Pulse** — can it take a request and return a token? latency, heartbeat, last response.
3. **Bloodwork** — logs, OOM/CUDA errors, context blowout, prompt/template corruption, tool-call failures.
4. **Neuro** — correct model, correct adapter, correct weights, sane sampling params, correct system prompt.
5. **History** — what changed last? deploy, config, weights, dependency, tool, API key, network, volume.
6. **Dx / Tx / Discharge** — diagnosis, treatment plan, and discharge decision.

## The three discharge outcomes

Every visit ends in exactly one of three:

- **`TREATMENT_REQUIRED`** — the agent has a hard fault. Fix it, then re-run the Doctor.
- **`OBSERVE`** — alive but degraded (slow, near limits). Watch it; do not promote yet.
- **`DISCHARGE_TO_EVAL_CURATOR`** — stable. `ready_for_eval_curator: true`. Hand it off.

Only a `DISCHARGE_TO_EVAL_CURATOR` receipt opens the door to the manager.

## Hard fault vs soft warning

Every finding is one of two severities — and the distinction *is* the decision:

- **`HARD_FAULT`** — the agent is broken. Blocks discharge. → `TREATMENT_REQUIRED`.
- **`SOFT_WARNING`** — alive but degraded (slow, near a ceiling). → `OBSERVE`.

Each finding also carries a **`root_cause_category`**:
`infra · model · retrieval · tool_call · prompt · context · network · auth · unknown`.
The dominant category drives the diagnosis, the treatment, and whether a human is needed.

## Receipts

Every visit produces a JSON receipt (see `schemas/swarm_doctor_receipt.schema.json`).
The receipt is the chart. It is the audit trail. No discharge without a receipt.

Each receipt also carries: `diagnosis_confidence` (0–1), `time_to_recovery_minutes`,
`human_required`, `last_known_good` (the recovery target), and a `receipt_sha256` so the
chart is tamper-evident. Agents may be identified by **ENS** (`agent01.client.defendable.eth`).

## Offline by default

Swarm-Doctor reads a local flight sheet and runs local probes (`systemctl` / `docker`)
only. No network calls, no cloud, no telemetry. **Source data never leaves the office.**

## Roster & continuity — next man up (locked)

A `dead`/`crash_loop` (any `TREATMENT_REQUIRED`) starter **always** opens a continuity
event. The position is **never silently vacant**, and activation **never grants untested
authority**. With a depth chart, the event resolves to exactly one outcome:

- **`BACKUP_RESTRICTED_DUTY`** — eligible pre-evaluated backup covers, using only its own approved reduced play set.
- **`HUMAN_FAILOVER_SAFE_MODE`** — no backup, but a human covers and the lane has a safe mode.
- **`OPERATIONS_SUSPENDED`** — fail-closed: nothing can safely cover → halt, preserve receipts, escalate.

Criticality controls paging urgency only (`critical→immediate_page`,
`material→urgent_notification`, `low_risk→log_and_queue_owner_notice`) — never whether the
event opens.

**Suspension paging — `PAGE_REQUIRED` (owner doctrine):** any **production** lane entering
`OPERATIONS_SUSPENDED` sets `escalation_urgency = PAGE_REQUIRED` — an explicit, active human
page to the owner / on-call authority, **regardless of role tier**. A suspended production
lane means the starter is unavailable, no eligible tested backup exists, no permitted safe
human continuation path exists, and the operation is halted because proceeding is unsafe —
that is always worth a page, never quiet handling. **Exemption:** lanes explicitly tagged
non-production (`environment: sandbox|test|non_production|dev|staging`, or
`non_production: true`) may follow ordinary tier policy when suspended.

**Health observation vs continuity action (no substitution without authorization):**
- `MONITOR` (from an `OBSERVE` health verdict) and `NO_CONTINUITY_EVENT` are **health
  observation outcomes** — `triggered: false`. They **do not activate substitution.**
- `BACKUP_RESTRICTED_DUTY`, `HUMAN_FAILOVER_SAFE_MODE`, `OPERATIONS_SUSPENDED` are the
  **continuity actions** — `triggered: true`.
- An `OBSERVE`/`MONITOR` result never moves the starter off the field or activates a backup
  unless a future flight-sheet rule explicitly authorizes restricted duty.

Continuity rides *alongside* the Doctor's verdict; it never grades quality.
See [`PLAYBOOK.md`](PLAYBOOK.md) §9 and [`examples/continuity_next_man_up.md`](examples/continuity_next_man_up.md).

## Where this fits in DefendableOS

Flight sheets, playbooks, referee review, receipts, eval-curator — Swarm-Doctor slots
in *upstream* of eval-curator and *shares the same grammar*: a machine-readable flight
sheet drives a Python referee runner that emits a signed-shape receipt.
