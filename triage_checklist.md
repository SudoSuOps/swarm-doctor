# Swarm-Doctor — Paper Triage Checklist

For when you want a stethoscope on the patient by hand. Tick each box, then transcribe
the numbers into `flight_sheet.yaml` → `observations` and run the CLI, OR just decide by
the rules at the bottom.

> Never grade answer quality. Health only. Doctor before manager.

## Admit
- [ ] agent_id (or ENS, e.g. agent01.client.defendable.eth): ______________________
- [ ] agent_name: ____________________
- [ ] host: __________________________
- [ ] symptom (what was seen): _______________________________________
- [ ] last_known_good (recovery target): _____________________________

## 1. Vitals  (circle one)
- [ ] Process running?  `ps` / `systemctl status` / `docker ps` / `pm2 list`
- [ ] vitals_state:  **alive  /  dead  /  crash_loop  /  hung  /  unreachable**
- [ ] crash_count in window: ______
- [ ] consecutive_failures: ______
> dead / crash_loop / unreachable → **hard fault**, skip to Dx.

## 2. Pulse
- [ ] Sent ___ probe requests; ___ succeeded  (need ≥ min_successful_probe_count)
- [ ] latency_ms (p95): ______
- [ ] heartbeats: ___ / ___ succeeded
- [ ] last_response_age_s: ______
> no token returned / heartbeat rate too low → **hung confirmed, hard fault**.

## 3. Bloodwork  (check any present)
- [ ] oom              (→ infra)
- [ ] cuda_error       (→ infra)
- [ ] context_blowout  (→ context)
- [ ] template_corruption (→ prompt)
- [ ] tool_call_failure   (→ tool_call)
- [ ] auth_error          (→ auth)
- [ ] retrieval_failure   (→ retrieval)
- [ ] errors: ___ / total_checks ___   → error_rate = ____
- [ ] GPU: used_vram ______ / total_vram ______
- [ ] context: used_tokens ______ / max_tokens ______
> any flag, or error_rate over budget → **hard fault**.

## 4. Neuro
- [ ] loaded_model == expected_model?   loaded: __________  expected: __________
- [ ] loaded_adapter == expected_adapter?   loaded: ________  expected: ________
- [ ] sampling sane (temp/top_p/max_tokens)?   Y / N
- [ ] system prompt present & correct?   Y / N
> any mismatch → **hard fault**. (This is the usual cause of "garbage outputs" — a
> wiring fault, not a quality score.)

## 5. History — what changed last?
- [ ] deploy ______  config ______  weights ______  dependency ______
- [ ] tool ______  API key ______  network ______  volume ______
- [ ] prime suspect (most recent change): _______________________________

## 6. Dx (one line): ___________________________________________________
- [ ] root_cause_category (circle): infra / model / retrieval / tool_call / prompt / context / network / auth / unknown
- [ ] diagnosis_confidence (0.0–1.0): ______
- [ ] human_required?  Y / N      est. time_to_recovery (min): ______

## 7. Tx (actions): ___________________________________________________

## 8. Discharge (circle one)
- **TREATMENT_REQUIRED** — any hard fault above
- **OBSERVE** — alive, no hard fault, but latency/GPU/context near or over a soft limit
- **DISCHARGE_TO_EVAL_CURATOR** — all clear → ready_for_eval_curator: TRUE
