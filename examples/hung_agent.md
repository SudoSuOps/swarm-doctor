# Example — Hung Agent

**Symptom:** "process up but no responses."

The tricky one: the body is warm (process up, VRAM allocated) but nothing comes back.

## Observations (flight sheet)
```yaml
vitals_state: hung
process_up: true
consecutive_failures: 6        # > max (2)
successful_heartbeats: 2 / 20
successful_probes: 0 / 5
latency_ms: 30000              # > max (8000)
gpu: { used_vram_mb: 22000, total_vram_mb: 24000 }   # 92% > max (90%)
recent_changes: ["traffic spike 08:00"]
```

## Runner output
```
  Vitals     : hung
  Pulse      : flatline
  Heartbeat  : 0.10   Probes ok: 0
  Latency    : 30000 ms   GPU mem: 92%
  Stability  : 38.0 / 100
  HARD FAULTS:
    - vitals: agent is hung
    - pulse: successful_probe_count 0 < min 3
    - pulse: heartbeat_success_rate 0.10 < min 0.95
  Warnings   :
    - pulse: latency_ms 30000 > max 8000
    - bloodwork: gpu_memory_used_pct 0.92 > max 0.9
  DISCHARGE  : TREATMENT_REQUIRED   (ready_for_eval_curator: False)
```

## Receipt (key fields)
```json
{ "vitals_status": "hung", "pulse_status": "flatline",
  "discharge_status": "TREATMENT_REQUIRED", "ready_for_eval_curator": false,
  "metrics": { "latency_ms": 30000, "gpu_memory_used_pct": 0.92, "stability_score": 38.0 } }
```

**Dx:** worker hung — pulse is a flatline despite the process being up; VRAM pinned at 92% and a traffic spike at 08:00 point at a stuck request / saturation deadlock.
**Tx:** kill and restart the hung worker, free VRAM, check for a deadlock or a stuck long request, consider concurrency/queue limits, then re-run the Doctor.
