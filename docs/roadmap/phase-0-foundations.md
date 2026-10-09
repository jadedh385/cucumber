# Phase 0 — Foundations

**Goal:** a deployable, tested, secured empty app with the building blocks every
feature needs: identity, permissions, audit, IDs, reference lists, backups.
No plant data yet.

**Release gate:** [R0](README.md#phase-release-gates)

Card format: *Source* = where the requirement comes from · *Deps* = units that
must pass G4 before this unit builds · *Decisions* = must be Resolved before G0
exits · *Gate focus* = unit-specific checks on top of [the standard gates](gates.md).

---

### U0.1 · Decision register & stack selection
- **Size:** M · **Deps:** — · **Decisions:** D-01, D-10, D-17
- **Scope:** resolve D-01 (standalone Cucumber vs inside Anemone) and choose stack:
  language, framework, database, hosting target, file storage. Record in an ADR.
  D-13 (Anemone's future) may stay Open; the ADR notes how it can join later.
- **Acceptance:** ADR approved; every Phase 0 decision Resolved; stack supports
  self-hosting, mobile-responsive web, transactional DB with constraints.
- **Gate focus:** G1 compare ≥ 2 options with a short spike each · G5 spike app
  deployed on the target host.

### U0.2 · Domain model v1
- **Size:** L · **Deps:** U0.1 · **Decisions:** D-02, D-05, D-07, D-15
- **Source:** SOP §3, §4, §5
- **Scope:** final ER model for `plants`, `batches`, `events`, reference lists,
  users, audit. Includes the decisions on vessel grain and deletion policy.
- **Acceptance:** every SOP rule (§5 1–8) maps to a DB constraint, a domain
  guard, or a documented reason it can't be enforced in the DB.
- **Gate focus:** G1 rule-to-enforcement table · G2 schema tests for uniqueness,
  FK, non-negative counts · G4 database review.

### U0.3 · Repository, CI & test harness
- **Size:** M · **Deps:** U0.1
- **Scope:** repo layout (by feature), lint, type check, unit / integration / E2E
  runners, coverage report with an 80 % threshold that fails CI.
- **Acceptance:** CI fails on lint error, type error, failing test, or coverage < 80 %.
- **Gate focus:** G2 a deliberately failing test proves CI blocks merge.

### U0.4 · Environments & self-hosted deployment
- **Size:** M · **Deps:** U0.3 · **Decisions:** D-10
- **Scope:** dev / staging / production; containerized deploy; secrets via
  environment variables; startup check that required secrets are present;
  feature flags.
- **Acceptance:** one command deploys to staging; app refuses to start with a
  missing secret; flags can toggle a feature without a redeploy.
- **Gate focus:** G4 security review (secrets, exposed ports) · G5 fresh-host deploy test.

### U0.5 · Authentication
- **Size:** M · **Deps:** U0.3, U0.4
- **Scope:** user accounts, login / logout, session expiry, password hashing,
  Owner-issued password reset, account deactivation.
- **Acceptance:** wrong password rejected without revealing whether the user exists;
  deactivated user can't log in; sessions expire.
- **Gate focus:** G4 **security review mandatory** · G2 tests for lockout and session expiry.

### U0.6 · Roles & permissions
- **Size:** M · **Deps:** U0.5 · **Decisions:** D-03
- **Source:** SOP §7, deck 05 "Role Access Control"
- **Scope:** 4 tiers enforced server-side on every endpoint. Master permission
  matrix lives here; every later unit adds rows at its G1.

| Action | Admin (Owner) | Supervisor | Tech (Staff) | Read Only |
|---|:-:|:-:|:-:|:-:|
| Register plant, create batch, log events | ✅ | ✅ | ✅ | — |
| Promote / demote / retire plant, assign SKU | ✅ | — | — | — |
| Review events, add corrections | ✅ | per D-03 | — | — |
| Edit reference lists | ✅ | — | — | — |
| See Zoho references | ✅ | — | — | — |
| View dashboards | ✅ | ✅ | ✅ | ✅ |
| Manage users | ✅ | — | — | — |

- **Acceptance:** every endpoint has a permission test for each role (allowed and denied).
- **Gate focus:** G2 role × endpoint test matrix generated, not hand-written · G4 security review.

### U0.7 · Audit trail & append-only event store
- **Size:** M · **Deps:** U0.2, U0.5 · **Decisions:** D-07
- **Source:** SOP §2.5, §5.6; deck 03 "Audit Trail"
- **Scope:** every write records user, timestamp, before/after. Event table is
  insert-only at the DB level. Archive / retire / deactivate actions require a reason.
- **Acceptance:** an UPDATE or DELETE on events fails at the DB; an archive
  without a reason is rejected; audit rows can't be edited by any role.
- **Gate focus:** G2 tests that try to mutate events through the API **and** raw SQL · G4 security review.

### U0.8 · ID sequence service
- **Size:** S · **Deps:** U0.2
- **Source:** SOP §3 IDs
- **Scope:** `PLT-nnnn`, `BAT-nnnnn`, `EVT-nnnnn`, SKU `<GENUS3><nnn>` per genus.
  Global, sequential, never reused, safe under concurrent writes.
- **Acceptance:** 100 parallel creates give 100 unique, never-reused IDs (gaps
  allowed); SKU sequence is per genus code.
- **Gate focus:** G2 concurrency test.

### U0.9 · Reference lists
- **Size:** S · **Deps:** U0.6, U0.7
- **Source:** SOP §3 (stages, media codes, locations, sources)
- **Scope:** Owner-editable lists: stages (codes locked, labels editable),
  media codes, locations (`Lab`, `Nursery` per D-14), genus codes, event actions
  (fixed). Items deactivate, never delete.
- **Acceptance:** stage codes `P0–P4, T1, C0` can't be renamed (shared with
  Protocol Tracking plan); deactivated item hidden from dropdowns, still shown on history.
- **Gate focus:** G5 Owner edits a media list on a phone.

### U0.10 · App shell & UI kit
- **Size:** M · **Deps:** U0.5 · **Decisions:** D-16, D-17
- **Scope:** navigation, global search box, form components (dropdowns for all
  coded fields, auto date / week), list + detail layouts, error and empty states,
  mobile-first. English UI, translation-ready (D-16).
- **Acceptance:** all components usable one-handed at 375 px width; date and week
  never typed; no UI text hard-coded outside the translation function (checked by
  a lint rule or test).
- **Gate focus:** G5 Staff UAT on the actual lab phone.

### U0.11 · Backup & restore baseline
- **Size:** S · **Deps:** U0.4
- **Scope:** scheduled DB + file backup to a second location; documented restore.
  (Encryption comes in U6.2.)
- **Acceptance:** restore of last night's backup into a clean staging host succeeds
  and passes the smoke test.
- **Gate focus:** G5 timed restore drill; result logged.
