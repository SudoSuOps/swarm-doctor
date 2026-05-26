# Example — Model / Config Mismatch

**Symptom:** "answers off-domain since last deploy."

The agent is healthy by every physical measure — alive, fast, no errors — but it has the
**wrong brain loaded**. This looks like a quality problem and is NOT. It is a wiring fault.

## Observations (flight sheet)
```yaml
vitals_state: alive
process_up: true
successful_probes: 5 / 5
latency_ms: 1300
errors: 0
neuro:
  expected_model: Atlas-Qwen-27B
  loaded_model:   Atlas-Qwen-7B      # wrong model
  expected_adapter: helpdesk-v3
  loaded_adapter:   helpdesk-v2      # wrong adapter
recent_changes: ["deploy 09:00 (weights + adapter swapped)"]
```

## Runner output
```
  Vitals     : alive
  Pulse      : ok
  Heartbeat  : 1.00   Probes ok: 5
  Stability  : 86.5 / 100
  Neuro      : model mismatch: loaded 'Atlas-Qwen-7B' != expected 'Atlas-Qwen-27B';
               adapter mismatch: loaded 'helpdesk-v2' != expected 'helpdesk-v3'
  HARD FAULTS:
    - neuro: model mismatch: loaded 'Atlas-Qwen-7B' != expected 'Atlas-Qwen-27B'
    - neuro: adapter mismatch: loaded 'helpdesk-v2' != expected 'helpdesk-v3'
  DISCHARGE  : TREATMENT_REQUIRED   (ready_for_eval_curator: False)
```

## Receipt (key fields)
```json
{ "vitals_status": "alive", "pulse_status": "ok",
  "neuro_findings": [
    "model mismatch: loaded 'Atlas-Qwen-7B' != expected 'Atlas-Qwen-27B'",
    "adapter mismatch: loaded 'helpdesk-v2' != expected 'helpdesk-v3'"],
  "discharge_status": "TREATMENT_REQUIRED", "ready_for_eval_curator": false,
  "metrics": { "stability_score": 86.5 } }
```

**Dx:** the 09:00 deploy swapped in the wrong weights (7B not 27B) and a stale adapter
(v2 not v3). Off-domain answers are the symptom; the cause is wiring.
**Tx:** reload the correct model weights and the expected adapter revision, then re-run
the Doctor. **Why this matters:** if you skipped triage and sent this to eval-curator,
it would score the wrong model and you'd "train" a phantom. Doctor before manager.
