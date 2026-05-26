# Example — Responding With Garbage

**Symptom:** "replies are gibberish / repeated tokens."

This is the one people want to send straight to eval-curator. **Don't.** Garbage output
is usually a *wiring* fault — corrupt chat template, broken system prompt, insane
sampling — not a quality-score problem. The Doctor fixes the wiring; only then does the
manager judge the answers.

## Observations (flight sheet)
```yaml
vitals_state: alive
process_up: true
successful_probes: 5 / 5      # it DOES respond...
latency_ms: 1500              # ...quickly...
bloodwork_flags: [template_corruption]
neuro: { sampling_sane: false, system_prompt_ok: false }   # ...but wired wrong
recent_changes: ["chat template edited 07:50"]
```

## Runner output
```
  Vitals     : alive
  Pulse      : ok
  Heartbeat  : 1.00   Probes ok: 5
  Stability  : 81.5 / 100
  Bloodwork  : template_corruption
  Neuro      : sampling params not sane; system prompt missing/garbled
  HARD FAULTS:
    - bloodwork: template_corruption
    - neuro: sampling params not sane
    - neuro: system prompt missing/garbled
  DISCHARGE  : TREATMENT_REQUIRED   (ready_for_eval_curator: False)
```

## Receipt (key fields)
```json
{ "vitals_status": "alive", "pulse_status": "ok",
  "bloodwork_findings": ["template_corruption"],
  "neuro_findings": ["sampling params not sane", "system prompt missing/garbled"],
  "discharge_status": "TREATMENT_REQUIRED", "ready_for_eval_curator": false,
  "metrics": { "stability_score": 81.5 } }
```

**Dx:** vitals and pulse are fine, but neuro + bloodwork are faulted — the 07:50 chat
template edit corrupted formatting and knocked out the system prompt / sampling. High
stability score (81.5) but **still TREATMENT_REQUIRED** because hard faults exist.
**Tx:** restore the correct system prompt, repair the chat template, reset sampling to
known-good values, then re-run the Doctor. The garbage is wiring, not the brain.
