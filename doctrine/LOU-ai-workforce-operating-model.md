# Letter of Understanding (LOU)
## DefendableOS — The AI Workforce Operating Model

**Date:** 2026-05-26
**Owner:** Donovan Mackey ("Mr D") — DefendableOS / SudoSuOps
**Builder:** Claude Code ("dev")
**Status:** Non-binding letter of understanding. This records a *shared mental model* and
an *agreed build order*. It is not a contract, a warranty, or a claim of capability we
have not yet built and tested.

---

## 1. Purpose

To put in writing the operating model we converged on: a company does not run AI agents
as "a bunch of bots." It runs a **disciplined, evaluated roster of digital workers** with
a chain of command, medical care, conditioning, backups, and a permanent evidence ledger
— the same way a franchise protects and deploys a high-value roster.

This LOU fixes three things so we don't drift:
1. The **org model** (who is responsible for what).
2. The **module map** and, honestly, **what is built vs. what is only specified**.
3. The **guardrails** that keep this from ballooning into vaporware.

---

## 2. The operating reality we agree on

> "It is a vicious game, but it is reality." — Mr D

Agents in critical workflows will fail, drift, lose tool access, make a dangerous call,
or simply be out-performed by a better player. A mature company plans for that *before*
the season, not after the injury. Therefore every critical workflow gets:

a **starter**, a **backup**, a **doctor**, a **conditioning program**, a **rehab path**,
a **return-to-work gate**, and a **record proving every decision**.

---

## 3. Chain of command (the front office)

| Role | Human/Agent | Responsibility |
|---|---|---|
| **Owner / CEO** | human | Owns business risk and asset decisions. Sees the roster. |
| **Coach / Ops Manager** | human or authorized orchestrator | Selects lineup, assigns plays, approves substitutions. |
| **Tribunal** | system + human | Enforces rules; grants return-to-duty clearance. |
| **Conditioning Coach** | system | Monthly readiness, drift, workload, promote/demote evidence. |
| **Swarm-Doctor** | system | Triage, diagnose, treat, discharge failed agents. |
| **Players** | agents | Perform assigned work within cleared permissions. |
| **Position Groups** | agent teams | Specialized rooms inside a department. |

**Principle:** no free-ranging agent with unlimited authority. Every agent answers to the
coach and the owner.

---

## 4. Module map and HONEST build status

| Module | Purpose | Status |
|---|---|---|
| **Swarm-Doctor** | Injury triage → diagnose → treat → discharge | **BUILT (v1.1, shipped)** |
| Receipt ledger | Hash-stamped audit trail per visit | **BUILT** (per-receipt sha256; chain ledger = roadmap) |
| Agent identity (ENS) | `agent01.client.defendable.eth` | **BUILT** (in receipts) |
| **Roster & Continuity** | Depth chart, backup activation, restricted-duty | **SPECIFIED (this LOU §5) — not built** |
| Conditioning Coach | Monthly readiness / drift / promote-demote | **SPECIFIED — not built** |
| Eval-Curator / Tribunal | Performance grade + return-to-work clearance | **EXISTS separately** (downstream of Doctor) |
| Team Film Review | Grade handoffs + end-to-end business outcome | **ROADMAP** |
| Agent Risk File | Evidence file for risk officers/insurers/buyers | **ROADMAP (evidence first, claims later)** |

> We will not describe a module as a capability until it is built **and** tested with
> receipts. Everything above marked SPECIFIED/ROADMAP is a design, not a product.

---

## 5. The Roster & Continuity layer (specified)

This is the agreed next design. It bolts directly onto Swarm-Doctor: when the Doctor
returns `TREATMENT_REQUIRED`, continuity activates "next man up."

### 5.1 Four roster statuses
- **STARTER** — best all-around trusted agent for the position.
- **ROTATIONAL** — cleared agent used for workload management or matchup advantage.
- **SPECIALIST** — narrow play where its tested skill is strongest.
- **BACKUP / FAILOVER** — prepared to step in when the primary is removed/restricted.

### 5.2 Depth chart (machine-readable, per position group)
```yaml
position_group: customer_support
roster:
  - agent_id: support-01.client.defendable.eth
    depth_chart: starter
    strengths: [complex_policy_reasoning, complaint_resolution]
    restrictions: [no_autonomous_refunds_over_250]
    last_conditioning: 2026-05-20        # staleness gates eligibility
  - agent_id: support-02.client.defendable.eth
    depth_chart: second_string
    strengths: [ticket_classification, fast_routing]
  - agent_id: support-03.client.defendable.eth
    depth_chart: specialist
    strengths: [refund_recommendation]
    restrictions: [human_approval_required_for_refund_execution]
human_coach: support_manager
```

### 5.3 Play-matching — best agent for the play, not the "best overall"
```yaml
plays:
  - play_id: classify_high_volume_queue
    assigned_agent: support-02.client.defendable.eth
    reason_receipt: sha256:...        # MUST cite an eval-curator receipt, not a vibe
  - play_id: resolve_complex_policy_dispute
    assigned_agent: support-01.client.defendable.eth
    reason_receipt: sha256:...
```
**Rule:** a play assignment is invalid without a backing eval receipt. Strengths are
*proven*, not asserted.

### 5.4 Substitution triggers
performance advantage · workload/fatigue equivalent · drift warning · incident/failure ·
restricted duty.

### 5.5 Continuity mode = REDUCED permissions (the highest-value safety piece)
```yaml
failure_protocol:
  critical_events: [agent_unreachable, unauthorized_action, hallucinated_policy, write_failure, data_exposure]
  immediate_action: [remove_starter_from_live_queue, activate_backup, require_human_approval, open_swarm_doctor_case, preserve_receipts]
backup_permissions:
  may: [classify, draft, route, annotate]
  may_not_without_human_approval: [issue_refunds, close_compliance_cases, make_policy_exceptions]
```
The backup running in **restricted duty** is not weakness — it is responsible continuity.

### 5.6 Two grades, not one
- **Player grade** — did this agent do its assignment? (eval-curator)
- **Team grade** — did the *handoffs* produce the correct business outcome? (Team Film Review)
A swarm can fail with every individual passing. Both grades are required.

---

## 6. Doctrine lines (the rules)

1. **Doctor before manager.** Triage health before grading performance. *(Swarm-Doctor)*
2. **No critical workflow depends on one untested agent.**
3. **No agent receives a play outside its cleared position.**
4. **The best agent for the assignment gets the play** — proven by receipt, not opinion.
5. **The coach and owner retain authority.** No unlimited autonomous agents.
6. **A backup that isn't tested is not a backup.** Stale conditioning = ineligible.
7. **Evidence before claims.** Build the record first; never market what isn't tested.

---

## 7. Scope discipline & guardrails

These exist because the vision is large and the failure mode is building a "giant
platform" that does nothing well. Agreed guardrails:

- **One brick at a time.** Each module ships built + tested before the next starts.
- **Metaphor is scaffolding, not the product.** Every "football" idea must convert to
  enforceable YAML + code + a receipt, or it stays in the deck. (Mr D's own instruction, twice.)
- **No insurance/warranty claims.** We build the *Agent Risk File* (evidence). We do not
  state, imply, or sell that DefendableOS "insures" or "certifies" agents until counsel
  and an actual underwriter say so. The receipt ledger is descriptive evidence, not a guarantee.
- **Offline by default.** Source data never leaves the office. Local flight sheets, local probes.
- **Receipts are the source of truth.** Strengths, clearances, and substitutions reference
  hashes, not assertions.

---

## 8. Risk & positioning notes (builder's flags)

- **Insurance liability is real.** The franchise insurance analogy is powerful for
  *internal risk framing*, dangerous as an *external promise*. Lead with the Risk File;
  let the customer's own insurer/risk officer draw conclusions.
- **Play-matching is only as good as its evidence pipeline.** Without eval-curator
  receipts feeding "strengths," the depth chart becomes theater. Build the evidence link first.
- **Module sprawl is the top risk to delivery.** Six new modules described in one sitting.
  Recommend building exactly one next (see §9).

---

## 9. Agreed next deliverable (proposed — pending owner go)

**Roster & Continuity v0.1**, scoped tight, bolted onto Swarm-Doctor:

1. A `depth_chart.yaml` schema (§5.2) + validator.
2. An extension to the Swarm-Doctor receipt: when `discharge_status == TREATMENT_REQUIRED`,
   emit a **continuity action** — name the backup, the restricted-duty permission set, and
   the human owner to notify. ("Next man up," made real and testable.)
3. One worked example (support agent on injured reserve → backup activated in restricted duty).
4. Self-test + CI, same discipline as v1.1.

Everything else in §4 (Conditioning Coach, Team Film Review, Risk File) stays SPECIFIED/
ROADMAP until this brick is shipped and reviewed.

---

## 10. Understanding

This LOU reflects the model and order of work we agree on as of 2026-05-26. It is a
direction-setting document. Build status is stated honestly above; nothing here claims a
capability that is not yet built and receipt-tested.

**Owner:** Donovan Mackey — DefendableOS / SudoSuOps
**Builder:** Claude Code (dev)
