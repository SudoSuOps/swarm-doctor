# Release Proof — Roster & Continuity v0.1

**Status:** CLOSED — owner verdict PASS; suspension paging doctrine corrected to `PAGE_REQUIRED`.
**Date:** 2026-05-26
**Repo:** `git@github.com:SudoSuOps/swarm-doctor.git`
**Release-content commit:** `a3c570644b5af18ede05e1ad1f355822715edbca`

Roster & Continuity bolts onto Swarm-Doctor: when the Doctor returns `TREATMENT_REQUIRED`,
the position is never silently vacant — a continuity event opens and resolves to exactly
one of three actions, written into the sha256-stamped receipt under `continuity_action`.

---

## 1. Final file tree

```
swarm-doctor/
  README.md  DOCTRINE.md  PLAYBOOK.md  triage_checklist.md  flight_sheet.yaml  .gitignore
  RELEASE-roster-continuity-v0.1.md          ← this proof
  cli/
    swarm_doctor.py                          ← runner: health math → receipt → continuity
  schemas/
    swarm_doctor_receipt.schema.json
    depth_chart.schema.json
  doctrine/
    LOU-ai-workforce-operating-model.md
  examples/
    dead_process.md  crash_loop.md  hung_agent.md  garbage_outputs.md
    model_config_mismatch.md  continuity_next_man_up.md
    sheets/
      healthy.yaml  dead.yaml  crash.yaml  hung.yaml  garbage.yaml  mismatch.yaml  observe.yaml
      dead_with_backup.yaml  dead_no_backup.yaml  dead_suspend.yaml
      dead_suspend_prod_lowrisk.yaml  dead_suspend_sandbox.yaml  dead_critical_backup.yaml
    depth_charts/
      customer_support.yaml  no_backup.yaml  payments_executor.yaml
      lowrisk_prod_batch.yaml  sandbox_batch.yaml  critical_support.yaml
  receipts/
    example_receipt.json  example_continuity_receipt.json
    release_v0.1/
      01_backup_restricted_duty.json
      02_human_failover_safe_mode.json
      03_operations_suspended.json
  .github/workflows/
    swarm-doctor-check.yml                   ← CI: runs the self-test
```

## 2. Test command

```bash
python3 cli/swarm_doctor.py --selftest examples/sheets
```
Also run in CI on every push/PR via `.github/workflows/swarm-doctor-check.yml`.
Depth charts validate with: `python3 cli/swarm_doctor.py --validate-depth-chart <path>`.

## 3. Test result — 13/13 PASS

```
[ok] crash.yaml                  TREATMENT_REQUIRED
[ok] dead.yaml                   TREATMENT_REQUIRED
[ok] dead_critical_backup.yaml   TREATMENT_REQUIRED   outcome=BACKUP_RESTRICTED_DUTY    urgency=immediate_page
[ok] dead_no_backup.yaml         TREATMENT_REQUIRED   outcome=HUMAN_FAILOVER_SAFE_MODE  urgency=immediate_page
[ok] dead_suspend.yaml           TREATMENT_REQUIRED   outcome=OPERATIONS_SUSPENDED      urgency=PAGE_REQUIRED
[ok] dead_suspend_prod_lowrisk   TREATMENT_REQUIRED   outcome=OPERATIONS_SUSPENDED      urgency=PAGE_REQUIRED
[ok] dead_suspend_sandbox        TREATMENT_REQUIRED   outcome=OPERATIONS_SUSPENDED      urgency=log_and_queue_owner_notice
[ok] dead_with_backup.yaml       TREATMENT_REQUIRED   outcome=BACKUP_RESTRICTED_DUTY    urgency=urgent_notification
[ok] garbage.yaml                TREATMENT_REQUIRED
[ok] healthy.yaml                DISCHARGE_TO_EVAL_CURATOR
[ok] hung.yaml                   TREATMENT_REQUIRED
[ok] mismatch.yaml               TREATMENT_REQUIRED
[ok] observe.yaml                OBSERVE
SELFTEST: PASS
```

### Owner-mandated escalation proof cases (all PASS)

| # | tier | environment | outcome | escalation_urgency |
|---|---|---|---|---|
| 1 | low_risk | **production** | OPERATIONS_SUSPENDED | **`PAGE_REQUIRED`** |
| 2 | low_risk | **sandbox** | OPERATIONS_SUSPENDED | `log_and_queue_owner_notice` |
| 3 | material | production | BACKUP_RESTRICTED_DUTY | `urgent_notification` |
| 4 | critical | production | BACKUP_RESTRICTED_DUTY | `immediate_page` |

## 4. One receipt per continuity outcome (with hashes)

Stored under `receipts/release_v0.1/`. Continuity blocks:

**① `BACKUP_RESTRICTED_DUTY`** — `01_backup_restricted_duty.json`
`sha256: 677b9f21bad8c2af1b4d5c4bd5c262f14caf80e12caecd1b6f24c1536fd05165`
```
outcome=BACKUP_RESTRICTED_DUTY  workflow=COVERED_BY_BACKUP
activated=support-02.helpdesk.defendable.eth
activated_permissions=[classify_tickets, draft_response, route_escalation, update_case_notes]
requires_human_approval=[issue_refund, close_compliance_case, make_policy_exception]
escalation_urgency=urgent_notification (tier material)
```

**② `HUMAN_FAILOVER_SAFE_MODE`** — `02_human_failover_safe_mode.json`
`sha256: 6991e5c4a75aaf54d87af24f2c5edfbf9a3742ad4a60c6485e12d56d05b16351`
```
outcome=HUMAN_FAILOVER_SAFE_MODE  workflow=COVERED_BY_HUMAN_SAFE_MODE
activated=none  (lane runs in safe mode under compliance_officer)
escalation_urgency=immediate_page (tier critical)
```

**③ `OPERATIONS_SUSPENDED`** — `03_operations_suspended.json`
`sha256: f3a9ab0db784bb3ac051a9671b172af4e6b264991a41128e80f3dfe3283e5632`
```
outcome=OPERATIONS_SUSPENDED  workflow=SUSPENDED  receipts_preserved=true  environment=production
activated=none  (all lane actions blocked pending human control)
escalation_urgency=PAGE_REQUIRED   ← explicit active human page (owner doctrine; not tier-derived)
```

## 5. Receipt hash verification result

Each receipt's `receipt_sha256` recomputed over the receipt minus that field
(canonical, sorted): **ALL HASHES VERIFIED: True**. All receipts also validate against
`schemas/swarm_doctor_receipt.schema.json`.

## 6. Doctrine locked in this release

- Continuity event **always** opens on a `dead`/`crash_loop` (any `TREATMENT_REQUIRED`) starter.
- Resolves to **exactly one**: `BACKUP_RESTRICTED_DUTY` / `HUMAN_FAILOVER_SAFE_MODE` / `OPERATIONS_SUSPENDED`.
- **Never untested authority:** only the backup's own approved play set is activated; a backup with no approved play set / benched / stale is ineligible.
- **Suspension paging = `PAGE_REQUIRED` (owner doctrine):** a **production** lane entering `OPERATIONS_SUSPENDED` sets `escalation_urgency = PAGE_REQUIRED` — an explicit active human page, regardless of tier. Non-production lanes (`environment: sandbox|test|non_production|dev|staging`) follow ordinary tier policy.
- **Covered events keep ordinary tier policy:** `BACKUP_RESTRICTED_DUTY` and `HUMAN_FAILOVER_SAFE_MODE` follow `criticality_tier` (the latter unless the chart sets `human_failover_page_required: true`).
- **Criticality controls paging urgency only**, never whether an event opens.
- **Health observation ≠ continuity action:** `MONITOR`/`NO_CONTINUITY_EVENT` (`triggered:false`) never activate substitution.

## 6a. Proof the stale "urgent_notification-only" production-suspension rule is removed

- Code: the previous `SUSPEND_PAGE_FLOOR = "urgent_notification"` and `_at_least()` floor are
  **deleted**; production suspension now assigns the explicit `URG_PAGE_REQUIRED = "PAGE_REQUIRED"`.
- Schema: `escalation_urgency` enum now includes `PAGE_REQUIRED`.
- Test: `dead_suspend_prod_lowrisk` (low_risk **production** suspend) asserts
  `expect_urgency: PAGE_REQUIRED` and passes — a low-tier production suspension can no longer
  resolve to a quiet `urgent_notification`.
- Repo grep for a production-suspension path emitting `urgent_notification`: none.

## 7. Known limitations

- **Observations are hand-entered** (except vitals, which `--probe` can read for real via
  `systemctl`/`docker`). Pulse/bloodwork/neuro are not yet auto-probed.
- **Activation is advisory, not enforcing.** The receipt *states* the outcome and the
  permitted play set; it does not itself revoke tokens or stop a process. Wiring the
  outcome to a real permission broker / process control is future work.
- **One depth chart = one position group.** No cross-group roster view in v0.1.
- **Eligibility staleness uses run-date vs `last_conditioning`.** Example charts set a large
  `conditioning_max_age_days` so dates never disqualify in CI; real lanes should set a real window.
- **Human availability is a declared flag**, not a live on-call lookup.
- **No persistence/ledger chaining.** Each receipt is independently hashed; receipts are not yet chained.

## 8. Explicitly OUT OF SCOPE for v0.1 (not built, by instruction)

- dashboard / web UI
- insurance or warranty layer
- play-matching engine (capability-based routing)
- conditioning module (monthly readiness)
- team handoff / outcome graph
- cloud sync (offline-only by design)
- enforcement/permission-broker integration (advisory output only)

---

**Brick closed.** Conditioning Coach not started, per instruction.
