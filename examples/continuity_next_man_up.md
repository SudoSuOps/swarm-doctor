# Example — Next Man Up (Roster & Continuity v0.1)

**Locked doctrine (Mr D):**
1. A `dead`/`crash_loop` primary **always** triggers a continuity event.
2. The position is **never silently vacant**.
3. Continuity activation **never grants untested authority**.
4. Eligible pre-evaluated backup → **`BACKUP_RESTRICTED_DUTY`** (activate only the backup's approved reduced play set).
5. No eligible backup → **`HUMAN_FAILOVER_SAFE_MODE`** (only the lane's safe-mode behavior).
6. Neither can proceed safely → **`OPERATIONS_SUSPENDED`** (preserve receipts + escalate).
7. **Criticality controls paging urgency, not whether an event opens:**
   - critical → `immediate_page`
   - material → `urgent_notification`
   - low_risk → `log_and_queue_owner_notice`

```
                        starter TREATMENT_REQUIRED  (dead / crash_loop)
                                  │  event ALWAYS opens
                     eligible pre-evaluated backup?
                        ┌─────────┴─────────┐
                       yes                  no
                        │          human owner AND lane safe mode?
                        │            ┌────────┴────────┐
                        │           yes                no
                        ▼            ▼                  ▼
                 BACKUP_         HUMAN_FAILOVER_     OPERATIONS_
                 RESTRICTED_DUTY SAFE_MODE           SUSPENDED
```

Run by pairing a flight sheet with a depth chart (validate it first):
```bash
python3 cli/swarm_doctor.py --validate-depth-chart examples/depth_charts/customer_support.yaml
python3 cli/swarm_doctor.py --flight-sheet examples/sheets/dead_with_backup.yaml \
  --depth-chart examples/depth_charts/customer_support.yaml
```

---

## Outcome 1 — support agent (the worked example) → `BACKUP_RESTRICTED_DUTY`

`customer_support` (tier **material**): starter `support-01` is dead; backup `support-02`
is eligible (cleared, not stale, has an approved play set).

```
  CONTINUITY : customer_support (tier material)  starter=INJURED_RESERVE
    outcome  : BACKUP_RESTRICTED_DUTY
    workflow : COVERED_BY_BACKUP
    activated: support-02.helpdesk.defendable.eth
    escalate : urgent_notification  →  owner support_manager (notified=True)
    limit    : activated play set (backup-approved only): classify_tickets, draft_response, route_escalation, update_case_notes
    limit    : human approval required: issue_refund
    limit    : coverage by backup agent — restricted duty, never starter authority
```

Only `support-02`'s **own approved** play set is activated — it can classify, draft, and
route, but **refunds/policy require a human**. No untested authority is ever granted.

## Outcome 2 — no eligible backup, lane has a safe mode → `HUMAN_FAILOVER_SAFE_MODE`

`compliance_review` (tier **critical**): the only backup is benched (`eligible: false`),
but a human owner exists and the lane has a safe mode (review/flag/draft only).

```
  CONTINUITY : compliance_review (tier critical)  starter=INJURED_RESERVE
    outcome  : HUMAN_FAILOVER_SAFE_MODE
    workflow : COVERED_BY_HUMAN_SAFE_MODE
    activated: — none —
    escalate : immediate_page  →  owner compliance_officer (notified=True)
    limit    : no eligible backup — lane runs in safe mode only (draft / read-only / queue-and-hold)
    limit    : human owner (compliance_officer) covers / authorizes until a backup is cleared
```

## Outcome 3 — nothing can safely cover → `OPERATIONS_SUSPENDED`

`payments_execution` (tier **critical**): no eligible backup and `safe_mode_available:
false` — "move money" has no draft/read-only version. **Fail-closed: stop the line.**

```
  CONTINUITY : payments_execution (tier critical)  starter=INJURED_RESERVE
    outcome  : OPERATIONS_SUSPENDED
    workflow : SUSPENDED
    activated: — none —
    escalate : immediate_page  →  owner treasury_controller (notified=True)
    limit    : OPERATIONS SUSPENDED — all agent actions blocked pending human control
    limit    : reason: lane has no safe degraded mode (actions are not reversible / holdable)
    limit    : receipts preserved; no work proceeds until a human assumes control or a backup is cleared
```

### Suspension paging floor + sandbox exemption

`OPERATIONS_SUSPENDED` on a **production** lane pages at minimum `urgent_notification`
regardless of tier (owner ruling). A lane tagged non-production may log instead:

```
dead_suspend_prod_lowrisk  (low_risk, environment: production) → urgency urgent_notification   (floored)
dead_suspend_sandbox       (low_risk, environment: sandbox)    → urgency log_and_queue_owner_notice  (exempt)
```

---

## What this proves

- A continuity event **always resolves to exactly one of the three locked outcomes** — exhaustive.
- **Never untested authority:** only the backup's own approved `permissions.may` is activated. A backup with no approved play set is ineligible (drops to human/suspend).
- Outcome 3 is **fail-closed** and **preserves receipts** before escalating.
- **Criticality drives only paging urgency** (`material→urgent_notification`, `critical→immediate_page`), never whether the event opens.
- The whole action rides inside the sha256-stamped receipt under `continuity_action`. It never grades quality or overrides the Doctor's health verdict.
