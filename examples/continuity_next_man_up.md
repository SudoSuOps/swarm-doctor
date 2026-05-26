# Example — Next Man Up (Roster & Continuity v0.1)

**Doctrine (Mr D, 2026-05-26):** the position is never vacant. A `dead`/`crash_loop`
starter — any `TREATMENT_REQUIRED` — **always** activates coverage, every tier, 24/7.
But coverage runs inside a **limitation envelope**: a backup steps in on *restricted
duty*, or if there's no eligible backup, the workflow drops to **human failover**.
Criticality tier doesn't decide *whether* we act — only *how loud we page*.

Run it by pairing a flight sheet with a depth chart:
```bash
python3 cli/swarm_doctor.py \
  --flight-sheet examples/sheets/dead_with_backup.yaml \
  --depth-chart  examples/depth_charts/customer_support.yaml
```
(or declare `depth_chart: ../depth_charts/customer_support.yaml` inside the sheet.)

---

## Case A — starter down, eligible backup exists → `BACKUP_RESTRICTED_DUTY`

Depth chart `customer_support` (tier **high**): starter `support-01`, eligible backup
`support-02`. The starter's service is dead.

```
  CONTINUITY : customer_support (tier high)  starter=INJURED_RESERVE
    coverage : BACKUP_RESTRICTED_DUTY
    activated: support-02.helpdesk.defendable.eth
    escalate : page  →  owner support_manager (notified=True)
    limit    : human approval required: issue_refund
    limit    : human approval required: close_compliance_case
    limit    : human approval required: make_policy_exception
    limit    : coverage by backup agent — restricted duty, not full starter authority
```

The backup keeps the queue moving (classify, draft, route) but **cannot move money or
policy without a human**. The position stayed covered; the starter went to the Doctor.

## Case B — starter down, no eligible backup → `HUMAN_FAILOVER_ONLY`

Depth chart `compliance_review` (tier **critical**): the only backup is benched
(`eligible: false` — failed/stale conditioning; *a backup that isn't tested is not a
backup*). The starter is crash-looping.

```
  CONTINUITY : compliance_review (tier critical)  starter=INJURED_RESERVE
    coverage : HUMAN_FAILOVER_ONLY
    activated: — none — HUMAN FAILOVER
    escalate : page_oncall  →  owner compliance_officer (notified=True)
    limit    : no eligible tested backup — workflow drops to safe mode (draft / read-only / queue-and-hold)
    limit    : human owner (compliance_officer) must cover or authorize until a backup is cleared
```

No warm body to activate, so the system does the safe thing: drop to safe mode and page
the on-call owner **loud** (critical tier). It does not pretend the position is covered.

---

## What this proves

- Activation is **unconditional** on a removed starter — exactly the doctrine.
- The **limitation envelope** is explicit and machine-readable (`backup_permissions`).
- **Tier drives paging**, not whether we act: `high → page`, `critical → page_oncall`.
- The whole action is inside the sha256-stamped receipt under `continuity_action`.
- Discharge logic is unchanged — continuity rides *alongside* the Doctor's verdict, it
  does not grade quality or override the health decision.
