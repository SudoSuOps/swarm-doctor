# Example — Dead Process

**Symptom:** "no replies; service not running."

## Observations (flight sheet)
```yaml
vitals_state: dead
process_up: false
successful_heartbeats: 0 / 20
successful_probes: 0 / 5
errors: 20 / 20
neuro: { loaded_model: null, expected_model: Atlas-Qwen-27B }   # nothing loaded
recent_changes: ["deploy 08:05 (systemd unit edited)"]
```

## Runner output
```
  Vitals     : dead
  Pulse      : flatline
  Heartbeat  : 0.00   Error rate : 1.00   Probes ok: 0
  Stability  : 23.5 / 100
  HARD FAULTS:
    - vitals: agent is dead
    - pulse: heartbeat_success_rate 0.00 < min 0.95
    - bloodwork: error_rate 1.00 > max 0.05
  DISCHARGE  : TREATMENT_REQUIRED   (ready_for_eval_curator: False)
```

## Receipt (key fields)
```json
{ "vitals_status": "dead", "pulse_status": "flatline",
  "discharge_status": "TREATMENT_REQUIRED", "ready_for_eval_curator": false,
  "metrics": { "stability_score": 23.5 } }
```

**Dx:** process is down — prime suspect is the 08:05 systemd unit edit.
**Tx:** restart the service, confirm it stays up, verify the model loads, then re-run the Doctor.
**Note:** the model/adapter "mismatch" findings are a side effect of nothing being loaded; they clear once the service is back. Do **not** send to eval-curator — a corpse can't be graded.
