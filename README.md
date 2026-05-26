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

# CLI check: run every example sheet and assert the expected discharge decision
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
    swarm_doctor.py              ← referee runner (health math → receipt → decision)
  schemas/
    swarm_doctor_receipt.schema.json
  receipts/
    example_receipt.json         ← a discharge-ready receipt
  examples/
    dead_process.md  crash_loop.md  hung_agent.md
    garbage_outputs.md  model_config_mismatch.md
    sheets/                      ← runnable flight sheets behind the examples + selftest
  .github/workflows/
    swarm-doctor-check.yml       ← CI: runs the selftest over examples/sheets
```

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
