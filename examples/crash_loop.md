# Example — Crash-Looping Agent

**Symptom:** "container keeps restarting."

## Observations (flight sheet)
```yaml
vitals_state: crash_loop
process_up: false
crash_count: 7          # > max_crash_count (0)
consecutive_failures: 7
successful_probes: 0 / 5
errors: 19 / 20
bloodwork_flags: [cuda_error]
recent_changes: ["CUDA driver bumped overnight", "dependency bump: torch"]
```

## Runner output
```
  Vitals     : crash_loop
  Pulse      : flatline
  Stability  : 16.8 / 100
  Bloodwork  : cuda_error
  HARD FAULTS:
    - vitals: agent is crash_loop
    - vitals: crash_count 7 > max 0
    - bloodwork: cuda_error
  DISCHARGE  : TREATMENT_REQUIRED   (ready_for_eval_curator: False)
```

## Receipt (key fields)
```json
{ "vitals_status": "crash_loop", "bloodwork_findings": ["cuda_error"],
  "discharge_status": "TREATMENT_REQUIRED", "ready_for_eval_curator": false,
  "metrics": { "stability_score": 16.8 } }
```

**Dx:** crash loop driven by a `cuda_error` — prime suspect is the overnight CUDA driver / torch bump.
**Tx:** stop the restart loop, inspect crash logs, roll back the driver/dependency change, confirm a clean start, then re-run the Doctor.
