# Example — Next Man Up (Roster & Continuity v0.1)

**Doctrine (Mr D):** the position is never vacant. A `dead`/`crash_loop` starter — any
`TREATMENT_REQUIRED` — **always** fires a continuity event, every tier, 24/7. That event
**must resolve to exactly one of three actions:**

1. **`ACTIVATE_ELIGIBLE_BACKUP_RESTRICTED_DUTY`** — a tested backup covers, on reduced permissions.
2. **`ACTIVATE_HUMAN_FAILOVER_SAFE_MODE`** — no backup, but a human covers and the workflow has a safe degraded mode.
3. **`SUSPEND_UNSAFE_WORKFLOW_PENDING_HUMAN_CONTROL`** — *fail-closed*: nothing can safely cover, so the line stops.

Criticality tier sets *how loud we page*, never *whether* we act.

```
                        starter TREATMENT_REQUIRED
                                  │
                     eligible tested backup?
                        ┌─────────┴─────────┐
                       yes                  no
                        │          human owner AND safe mode?
                        │            ┌────────┴────────┐
                        │           yes                no
                        ▼            ▼                  ▼
                 ACTIVATE_      ACTIVATE_           SUSPEND_UNSAFE_
                 ELIGIBLE_      HUMAN_FAILOVER_     WORKFLOW_PENDING_
                 BACKUP_        SAFE_MODE           HUMAN_CONTROL
                 RESTRICTED_DUTY
```

Run it by pairing a flight sheet with a depth chart:
```bash
python3 cli/swarm_doctor.py --flight-sheet examples/sheets/dead_with_backup.yaml \
  --depth-chart examples/depth_charts/customer_support.yaml
```
(or declare `depth_chart: ../depth_charts/...` inside the sheet.)

---

## Outcome 1 — eligible backup → `ACTIVATE_ELIGIBLE_BACKUP_RESTRICTED_DUTY`

`customer_support` (tier **high**): backup `support-02` is eligible.

```
  CONTINUITY : customer_support (tier high)  starter=INJURED_RESERVE
    action   : ACTIVATE_ELIGIBLE_BACKUP_RESTRICTED_DUTY
    workflow : COVERED_BY_BACKUP
    activated: support-02.helpdesk.defendable.eth
    escalate : page  →  owner support_manager (notified=True)
    limit    : human approval required: issue_refund
    limit    : coverage by backup agent — restricted duty, not full starter authority
```
Queue keeps moving; the backup can't move money/policy without a human.

## Outcome 2 — no backup, human can cover safely → `ACTIVATE_HUMAN_FAILOVER_SAFE_MODE`

`compliance_review` (tier **critical**): the only backup is benched (`eligible: false`),
but a human owner exists and the workflow *has* a safe mode (review/flag/draft only).

```
  CONTINUITY : compliance_review (tier critical)  starter=INJURED_RESERVE
    action   : ACTIVATE_HUMAN_FAILOVER_SAFE_MODE
    workflow : COVERED_BY_HUMAN_SAFE_MODE
    activated: — none —
    escalate : page_oncall  →  owner compliance_officer (notified=True)
    limit    : no eligible backup — workflow runs in safe mode (draft / read-only / queue-and-hold)
    limit    : human owner (compliance_officer) covers / authorizes until a backup is cleared
```

## Outcome 3 — nothing can safely cover → `SUSPEND_UNSAFE_WORKFLOW_PENDING_HUMAN_CONTROL`

`payments_execution` (tier **critical**): no eligible backup, and `safe_mode_available:
false` — "move money" has no draft/read-only version. **Fail-closed: stop the line.**

```
  CONTINUITY : payments_execution (tier critical)  starter=INJURED_RESERVE
    action   : SUSPEND_UNSAFE_WORKFLOW_PENDING_HUMAN_CONTROL
    workflow : SUSPENDED
    activated: — none —
    escalate : page_oncall  →  owner treasury_controller (notified=True)
    limit    : WORKFLOW SUSPENDED — all agent actions blocked pending human control
    limit    : reason: workflow has no safe degraded mode (actions are not reversible/holdable)
    limit    : no work proceeds until a human assumes control or a backup is cleared
```

---

## What this proves

- A continuity event **always resolves to exactly one of the three actions** — the set is exhaustive.
- Outcome 3 is **fail-closed**: when in doubt, the workflow halts rather than running uncovered. Safer to stop a payment run than to limp it.
- Tier drives **paging loudness** (`high→page`, `critical→page_oncall`); suspension floors urgency at `page`.
- The whole action — including `workflow_status` and `limitations` — rides inside the sha256-stamped receipt under `continuity_action`. It never grades quality or overrides the Doctor's health verdict.
