# Swarm-Doctor

**Triage skill for sick AI agents. Doctor before manager.**

`eval-curator` grades healthy agents. Swarm-Doctor is the shrink that revives and
stabilizes a dead / hung / crash-looping / confused agent **first**, then discharges a
stable patient to eval-curator. It never grades answer quality.

Read [`DOCTRINE.md`](DOCTRINE.md) (2 minutes) for the why.

## Flow

```
flight_sheet.yaml
      ↓
swarm_doctor.py
      ↓
health math + checks
      ↓
receipt.json
      ↓
decision:
treat / observe / discharge
```

## Quick start

```bash
cd skills/swarm-doctor

# Run the referee runner against a flight sheet (uses the observations block in the sheet)
python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml

# Write the receipt somewhere specific
python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --out receipts/visit.json

# Run ONE real vitals probe and override observed vitals with ground truth
python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe docker:my-agent
python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe systemctl:my-agent.service

# Roster & continuity: a removed starter activates next-man-up (backup or human failover)
python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --depth-chart examples/depth_charts/customer_support.yaml

# CLI check: run every example sheet and assert the expected discharge decision (+ coverage)
python3 cli/swarm_doctor.py --selftest examples/sheets
```

**Offline by default.** The runner reads a local flight sheet and runs local probes
(`systemctl` / `docker`) only. No network, no cloud, no telemetry — **source data never
leaves the office.**

The CLI loads the flight sheet, computes health metrics, applies the thresholds, and
prints + saves a JSON receipt ending in one of:

- `TREATMENT_REQUIRED`
- `OBSERVE`
- `DISCHARGE_TO_EVAL_CURATOR`

Prefer pen and paper? Use [`triage_checklist.md`](triage_checklist.md) and fill the
[`flight_sheet.yaml`](flight_sheet.yaml) by hand.

## File tree

```
skills/swarm-doctor/
  README.md                      ← you are here
  DOCTRINE.md                    ← the why, in 2 minutes
  PLAYBOOK.md                    ← step-by-step triage procedure
  flight_sheet.yaml              ← machine-readable thresholds + observations
  triage_checklist.md            ← human paper checklist
  cli/
    swarm_doctor.py              ← referee runner (health math → receipt → decision → continuity)
  schemas/
    swarm_doctor_receipt.schema.json
    depth_chart.schema.json      ← roster / next-man-up schema
  receipts/
    example_receipt.json         ← a discharge-ready receipt
    example_continuity_receipt.json  ← a receipt with a continuity action
  doctrine/
    LOU-ai-workforce-operating-model.md  ← the franchise operating model (LOU)
  examples/
    dead_process.md  crash_loop.md  hung_agent.md
    garbage_outputs.md  model_config_mismatch.md
    continuity_next_man_up.md    ← roster continuity worked example
    sheets/                      ← runnable flight sheets behind the examples + selftest
    depth_charts/                ← runnable depth charts (roster definitions)
  .github/workflows/
    swarm-doctor-check.yml       ← CI: runs the selftest over examples/sheets
```

## Roster & Continuity (v0.1)

The position is never silently vacant. Pair a flight sheet with a **depth chart**; a
removed starter (`TREATMENT_REQUIRED`) always fires a continuity event, written into the
receipt as `continuity_action`. The event **resolves to exactly one of three outcomes:**

1. **`BACKUP_RESTRICTED_DUTY`** — eligible pre-evaluated backup covers, using only its approved reduced play set (never untested authority).
2. **`HUMAN_FAILOVER_SAFE_MODE`** — no backup, but a human covers and the lane has a safe degraded mode.
3. **`OPERATIONS_SUSPENDED`** — *fail-closed*: nothing can safely cover → stop the line, preserve receipts, escalate.

Criticality controls paging urgency only: `critical→immediate_page`, `material→urgent_notification`,
`low_risk→log_and_queue_owner_notice` — never *whether* the event opens. **Suspension paging:**
a **production** lane that hits `OPERATIONS_SUSPENDED` sets `escalation_urgency = PAGE_REQUIRED`
(explicit active human page) regardless of tier; lanes tagged `environment: sandbox|test|non_production`
follow ordinary tier policy instead.

`MONITOR` (from an `OBSERVE` health verdict) is a health-observation outcome, **not** a
continuity action — it never activates substitution.

Validate a depth chart before using it: `python3 cli/swarm_doctor.py --validate-depth-chart <path>`.

See [`examples/continuity_next_man_up.md`](examples/continuity_next_man_up.md) and
[`doctrine/LOU-ai-workforce-operating-model.md`](doctrine/LOU-ai-workforce-operating-model.md).

## What the receipt tells the operator (v1.1)

Beyond the discharge decision, every receipt carries:

- **`findings[]`** — explicit `HARD_FAULT` / `SOFT_WARNING` taxonomy, each tagged with a `category`.
- **`root_cause_category`** — one of `infra · model · retrieval · tool_call · prompt · context · network · auth · unknown` (`none` when healthy).
- **`diagnosis_confidence`** — 0–1 certainty in the diagnosis.
- **`time_to_recovery_minutes`** — operator estimate to get back to healthy.
- **`human_required`** — does a human need to step in, or can this be auto-treated?
- **`last_known_good`** — the recovery target (what "back to normal" means).
- **`vitals_probe`** — raw output of the real probe, when `--probe` was used (operator trust).
- **`receipt_sha256`** — tamper-evident hash over the whole receipt.
- **`agent_ens`** — ENS identity, e.g. `agent01.client.defendable.eth`.

## The flight sheet is code, not a doc

`flight_sheet.yaml` is **machine-readable instructions for the referee runner**. It
carries numeric thresholds (latency, error rate, heartbeat rate, GPU %, context %,
crash count) and an `observations` block the runner reads. Change the patient → change
the observations; change the standard → change the thresholds.

## Handoff to eval-curator

When `ready_for_eval_curator: true`, the receipt is the green light. eval-curator reads
`agent_id`, confirms `discharge_status == DISCHARGE_TO_EVAL_CURATOR`, and only then
begins grading. See "Discharge handoff" in [`PLAYBOOK.md`](PLAYBOOK.md).

## Related DefendableOS Modules

DefendableOS is built as a chain of single-purpose modules:

- **Swarm-Doctor** — triage and continuity evidence for failed or unhealthy agents. <https://github.com/SudoSuOps/swarm-doctor>
- **Conditioning Coach** — advisory preventive readiness and drift review. <https://github.com/SudoSuOps/conditioning-coach>
- **Owner Roster Registry** — records validated evidence and owner-approved roster state. <https://github.com/SudoSuOps/owner-roster-registry>
- **Permission Broker** — locally enforces broker-routed action permissions against mock support tools only. <https://github.com/SudoSuOps/permission-broker>

**Validation status:** Builder-produced public prototype. Independent Tribunal code audit and cross-module behavioral validation are pending. No production deployment, external SaaS restriction, live permission revocation, blockchain/ENS implementation, insurance coverage, or certification is claimed.
