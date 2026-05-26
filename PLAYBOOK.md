# Swarm-Doctor — Triage Playbook

Step-by-step procedure for one visit. Work top to bottom. Stop and treat at the first
hard fault; you do not need to finish the chart to call `TREATMENT_REQUIRED`.

**Golden rule:** never grade answer quality here. That is eval-curator's job, and only
after discharge.

---

## 0. Admit the patient

1. Open `flight_sheet.yaml`. Fill the `agent` block: `agent_id`, `agent_name`, `host`,
   `symptom` (what the operator saw — "stopped replying", "OOM on startup", etc.).
2. Fill the `observations` block with what you measure (or let future automation fill
   it — see TODOs in `cli/swarm_doctor.py`).

---

## 1. Vitals — is it alive?

Decide one `vitals_state`: `alive | dead | crash_loop | hung | unreachable`.

- **dead** — process not running. `ps`, `systemctl status`, `docker ps`, `pm2 list`.
- **crash_loop** — restarting repeatedly. Check restart count / `crash_count`.
- **hung** — process up, accepts nothing, returns nothing. (Confirm with Pulse.)
- **unreachable** — alive on host but you can't reach it (ingress/network/port).
- **alive** — running and reachable.

> `dead`, `crash_loop`, `unreachable` → hard fault. Record and go to Dx; you can skip
> deeper probes until the body is back.

**Real probe (recommended for vitals):** instead of trusting a hand-entered
`vitals_state`, let the runner read ground truth:
> ```
> python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe docker:<name>
> python3 cli/swarm_doctor.py --flight-sheet flight_sheet.yaml --probe systemctl:<unit>
> ```
> The probe runs locally (`docker inspect` / `systemctl show`), overrides
> `vitals_state`/`process_up`/`crash_count`, and records its raw output in the receipt's
> `vitals_probe` field. No network — source data never leaves the office.

## 2. Pulse — can it take a request and return a token?

- Fire `min_successful_probe_count` test requests. Count `successful_probes`.
- Record `latency_ms` (use the slowest acceptable, e.g. p95).
- Record heartbeats: `successful_heartbeats / total_heartbeats`.
- Record `last_response_age_s` (how long since it last said anything).
- Record `consecutive_failures` (longest current run of failed probes).

> No token comes back, or heartbeat rate below `min_heartbeat_success_rate` → the
> "hung" diagnosis is confirmed. Hard fault.

## 3. Bloodwork — read the logs

Pull recent logs and flag any of:

- `oom` — out of memory (host RAM or VRAM)            → category `infra`
- `cuda_error` — CUDA / driver / device fault          → category `infra`
- `context_blowout` — request exceeded context window  → category `context`
- `template_corruption` — broken chat template/prompt   → category `prompt`
- `tool_call_failure` — tool/function calls erroring     → category `tool_call`
- `auth_error` — API key / credential / auth failure     → category `auth`
- `retrieval_failure` — retrieval backend/index failure  → category `retrieval`

Also compute `error_rate = errors / total_checks`.

> Any critical flag, or `error_rate > max_error_rate` → hard fault. `oom` specifically
> points at GPU memory or context size.

## 4. Neuro — is the right brain loaded, wired right?

- `loaded_model` == `expected_model`?
- `loaded_adapter` == `expected_adapter`? (LoRA / adapter / weights revision)
- Sampling params sane? (temp, top_p, max_tokens not absurd) → `sampling_sane`
- System prompt correct and present? → `system_prompt_ok`

> Wrong model, wrong adapter, insane sampling, or missing/garbled system prompt →
> hard fault. **This is the usual cause of "responding with garbage."** It is NOT a
> quality-score problem; it is a wiring problem the Doctor fixes.

## 5. History — what changed last?

List `recent_changes`: deploy, config edit, weights swap, dependency bump, tool change,
API key rotation, network change, volume remount. The most recent change is your
prime suspect. History rarely fails the patient by itself — it tells you where to look.

## 6. Dx — diagnosis

State the single most likely cause in one line. Tie it to the section that failed.

## 7. Tx — treatment plan

Concrete next actions. Examples:
- restart the service / clear the crash loop
- roll back the last deploy or weights swap
- reduce `max_context_tokens` or batch size to clear OOM
- repair the chat template / restore the system prompt
- reload the correct adapter
- rotate / restore the API key

## 8. Discharge decision

Let the runner decide (or apply the same rules by hand):

- **`TREATMENT_REQUIRED`** — any hard fault. Treat, then re-run the Doctor.
- **`OBSERVE`** — alive, no hard fault, but a soft warning (latency over budget, GPU or
  context near the ceiling). Watch; do not promote.
- **`DISCHARGE_TO_EVAL_CURATOR`** — all clear. Set `ready_for_eval_curator: true`.

---

## Discharge handoff to eval-curator

A clean discharge produces a receipt with:

```json
{
  "agent_id": "agent01.helpdesk.defendable.eth",
  "agent_ens": "agent01.helpdesk.defendable.eth",
  "discharge_status": "DISCHARGE_TO_EVAL_CURATOR",
  "ready_for_eval_curator": true,
  "root_cause_category": "none",
  "diagnosis_confidence": 0.95,
  "human_required": false,
  "time_to_recovery_minutes": 0,
  "metrics": { "stability_score": 100.0 },
  "offline_mode": true,
  "timestamp": "...",
  "receipt_sha256": "..."
}
```

Handoff contract:

1. Swarm-Doctor writes the receipt to `receipts/`.
2. eval-curator reads it, confirms `discharge_status == "DISCHARGE_TO_EVAL_CURATOR"`
   **and** `ready_for_eval_curator == true`.
3. Only then does eval-curator begin grading turns against its rubric.
4. If either field is wrong, eval-curator refuses the patient and bounces it back to
   the Doctor. **No grading of an unhealthy agent. Ever.**

The receipt is the baton. The Doctor stabilizes; the manager grades. Two jobs, one
clean handoff.
