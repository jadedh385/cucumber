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
- **ADR:** [ADR-0001 Stack selection](adr/0001-stack-selection.md). Stack decided
  2026-10-09; D-10 Resolved (Cloudflare Access gate); D-17 Resolved (online only).
  Hosting decided 2026-10-11: self-hosted, starting on the Owner's spare
  MacBook Air, with a Singapore cloud VPS as the fallback if it proves a
  hassle. File storage: local disk, R2 later. UI kit: **daisyUI**, chosen
  from the spike 2026-10-11; the spike is deployed on the self-hosted machine
  for G5 and checked on an Android phone.

### U0.2 · Domain model v1
- **Split 2026-10-11** (architect review H5) into two units that share one spec
  and design note:
  - **U0.2a · Schema** (M, Deps: U0.1, U0.3): all tables, checks, foreign keys,
    triggers, database permissions and seed data. AC 1–4a, 4c–4e, 5–5b, 6–12,
    13–16c, 18, 19, 20, 21.
  - **U0.2b · Event core services** (M, Deps: U0.2a): the projection ("the
    count wins"), row locking, Void, Correction, Close, Split,
    genus reclassification, review rules, duplicate-save guard,
    `check_projections`. AC 4b, 12a–c, 16d–g, 17, 17a, 19a–d.
- **Size:** L (as two M units) · **Deps:** U0.1 · **Decisions:** D-02, D-05, D-07, D-15
- **Source:** SOP §3, §4, §5
- **Scope:** final ER model for `plants`, `batches`, `events`, reference lists,
  users, audit. Includes the decisions on vessel grain and deletion policy.
- **Acceptance:** every SOP rule (§5 1–13) maps to a DB constraint, a domain
  guard, or a documented reason it can't be enforced in the DB.
- **Gate focus:** G1 rule-to-enforcement table · G2 schema tests for uniqueness,
  FK, non-negative counts · G4 database review.
- **Unit files:** [spec (G0)](units/u0.2-spec.md) · [design note (G1 passed)](units/u0.2-design.md)

### U0.3 · Repository, CI & test harness
- **Unit files:** [spec (G0)](units/u0.3-spec.md) · [design note (G1 passed)](units/u0.3-design.md)
- **Size:** M · **Deps:** U0.1
- **Scope:** repo layout (by feature), lint, type check, unit / integration / E2E
  runners, coverage report with an 80 % threshold that fails CI. Release notes
  tooling from the [release process](release-process.md): git-cliff config,
  and the *Draft release* workflow (date versions `YYYY.MM.N`).
- **Acceptance:** CI fails on lint error, type error, failing test, or coverage < 80 %.
- **Gate focus:** G2 a deliberately failing test proves CI blocks merge.

### U0.4 · Environments & self-hosted deployment
- **Split 2026-10-12** (Owner) into two units that share one spec:
  - **U0.4a · App packaging & deploy** (M, Deps: U0.3): container image,
    compose files, secrets and start-up checks, production security settings,
    deploy command, feature flags (django-waffle), Discord release hook. AC1–AC14.
  - **U0.4b · Hosts, Cloudflare & go-live readiness** (M, Deps: U0.4a): DNS
    move to Cloudflare (D-25), staging as a second copy on the MacBook (D-26), Tunnel +
    Access, remote SSH, uptime alert, restart tests, staging E2E and
    walk-throughs. AC15–AC27.
- **Size:** L (as two M units) · **Deps:** U0.3 · **Decisions:** D-10, D-25, D-26
- **Scope:** dev / staging / production; containerized deploy; remote access via
  Cloudflare Tunnel + Access (D-10), no open inbound ports; secrets via
  environment variables; startup check that required secrets are present;
  feature flags. Every container (database included) restarts on its own after
  a reboot (`restart: unless-stopped`; the spike's database didn't, see the
  [setup log](runbooks/macbook-server-setup.md#setup-log)). Host set-up from the
  [ADR checklist](adr/0001-stack-selection.md#set-up-checklist-u04): power and
  sleep settings, UPS for the router, FileVault decision, remote management
  through Cloudflare Access, and an uptime alert to the Owner. Deploys go out
  from a release tag; publishing the GitHub Release posts the staff
  note to Discord ([release process](release-process.md)).
- **Acceptance:** one command deploys to staging; app refuses to start with a
  missing secret; flags can toggle a feature without a redeploy.
- **From U0.2b G5 (Owner, 2026-10-12):** once staging exists, deploy U0.2b there,
  run the full E2E suite, and re-run the Owner walk-through `uat/u0_2b.sh`.
  Same for U0.2a (G5, 2026-10-12): re-run `uat/u0_2a.sh` there.
- **From the U0.2b G4 review:** set a PostgreSQL `lock_timeout` for the app (a save that waits minutes for a lock can fail the 5-minute future-date check); if a connection pooler (PgBouncer, transaction mode) is used, `check_projections` must not stream with server-side cursors (`.iterator()`).
- **From the U0.3 G4 review:** production security settings (`SECURE_PROXY_SSL_HEADER`
  for Cloudflare, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS,
  `CSRF_TRUSTED_ORIGINS`, a `LOGGING` config) with `manage.py check --deploy`
  clean; the server sets `DB_USER=cucumber_app` and never `DJANGO_DEBUG=1`.
  Collaborators stay Owner + Claude only: the free plan can't protect tags or
  restrict who runs the *Draft release* workflow.
- **Gate focus:** G4 security review (secrets, exposed ports) · G5 fresh-host deploy test,
  including a restart test (the app comes back after a reboot and the FileVault password).
- **Unit files:** [spec (G0)](units/u0.4-spec.md)

### U0.5 · Authentication
- **Size:** M · **Deps:** U0.3, U0.4a
- **Scope:** user accounts, login / logout, session expiry, password hashing,
  Owner-issued password reset, account deactivation.
- **Acceptance:** wrong password rejected without revealing whether the user exists;
  deactivated user can't log in; sessions expire.
- **From the U0.1 spike review:** tests for a good login, a bad password, POST-only
  logout (GET refused), an unauthenticated save refused with no row written, a
  `?next=//evil.example` redirect refused, and CSRF with `enforce_csrf_checks`
  (the default test client skips CSRF). An HTMX request with an expired session
  gets **401 + `HX-Redirect`** to login, never a login page swapped into the form.
- **From the U0.3 G4 review:** set `LOGIN_REDIRECT_URL` (today a login lands on
  Django's `/accounts/profile/`, a 404); replace U0.3's minimal login template;
  login rate limiting. Password rules (Django's four validators) are already on.
- **Gate focus:** G4 **security review mandatory** · G2 tests for lockout and session expiry.
- **Unit files:** [spec (G0 passed)](units/u0.5-spec.md)

### U0.6 · Roles & permissions
- **Size:** M · **Deps:** U0.5 · **Decisions:** D-03
- **Source:** SOP §7, deck 05 "Role Access Control"
- **Scope:** 4 tiers enforced server-side on every endpoint. Master permission
  matrix lives here; every later unit adds rows at its G1.

| Action | Admin (Owner) | Supervisor | Tech (Staff) | Read Only |
|---|:-:|:-:|:-:|:-:|
| Register plant, create batch, log events | ✅ | ✅ | ✅ | — |
| Promote / demote / retire plant, assign SKU | ✅ | — | — | — |
| Review events, add corrections | ✅ | ✅ except events they did or saved (D-03, U0.2 M5) | — | — |
| Split, close, record loss | ✅ | ✅ | ✅ | — |
| Undo an entry they saved, within 10 minutes (D-07) | ✅ | ✅ | ✅ | — |
| Review Voids (including Undo) | ✅ | — | — | — |
| Reclassify a plant's genus (new SKU) | ✅ | — | — | — |
| Complete the Zoho link (vendor, `zoho_ref`) | ✅ | — | — | — |
| Enter work done by another staff member | ✅ | ✅ | — | — |
| Release a batch from quarantine | ✅ | ? | ? | — |
| Edit reference lists | ✅ | — | — | — |
| See Zoho references | ✅ | — | — | — |
| View dashboards | ✅ | ✅ | ✅ | ✅ |
| Manage users | ✅ | — | — | — |

- **Acceptance:** every endpoint has a permission test for each role (allowed and denied);
  a Supervisor can't review or correct an event they did or saved (D-03).
  Rows marked **?** are decided at U0.6 G1 (added by U0.2 architect review M6).
- **Granting and removing roles** (Owner 2026-10-12): the Admin gives, changes
  or removes a user's role; the change applies on the user's next request
  (no stale session keeps the old role); every change is recorded (who, when,
  old role → new role) in the audit trail (U0.7); the last Admin can't be
  removed or deactivated. Tested allowed and denied like any endpoint.
- **Role checks inside the event services** (U0.2b G4 security review, H1/H2,
  Owner 2026-10-12): the services check the caller, not only the views. Void
  and Correction only for roles allowed above; Undo only by `recorded_by`
  within 10 minutes of `recorded_at`; a Tech's `staff_id` must be themselves
  (N7); a deactivated user can't save anything. Until U0.6 the services
  trust their caller (design §3.1); no screen reaches them before then.
  Also: a resent `operation_id` returns the original result to anyone;
  check it is the same `recorded_by` (U0.2b G4 security L3).
- **Gate focus:** G2 role × endpoint test matrix generated, not hand-written · G4 security review.

### U0.7 · Audit trail & append-only event store
- **Size:** M · **Deps:** U0.2b, U0.5 · **Decisions:** D-07
- **Source:** SOP §2.5, §5.6; deck 03 "Audit Trail"
- **Scope:** every write records user, timestamp, before/after. Event table is
  insert-only at the DB level. Archive / retire / deactivate / **void** actions
  require a reason. Void and 10-minute Undo per D-07; staff anonymisation on request.
- **Acceptance:** an UPDATE or DELETE on events fails at the DB; an archive or
  void without a reason is rejected; Undo is refused after 10 minutes or for
  an event someone else saved; audit rows can't be edited by any role.
- **Gate focus:** G2 tests that try to mutate events through the API **and** raw SQL · G4 security review.

### U0.8 · ID sequence service
- **Size:** S · **Deps:** U0.2a
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
  (fixed). Items deactivate, never delete. Container types and counting units
  may join these lists, depending on D-22.
- **Acceptance:** stage codes `P0–P4, A1, T1, C0` can't be renamed (events
  reference them); each stage has a sort order, with A1 between P2 and P4 (D-06);
  deactivated item hidden from dropdowns, still shown on history.
- **Gate focus:** G5 Owner edits a media list on a phone.

### U0.10 · App shell & UI kit
- **Size:** M · **Deps:** U0.5 · **Decisions:** D-16, D-17
- **Scope:** navigation, global search box, form components (dropdowns for all
  coded fields, auto date / week), list + detail layouts, error and empty states,
  mobile-first. English UI, translation-ready (D-16). Built on **Tailwind +
  daisyUI 5** (ADR-0001), CSS compiled by the Tailwind standalone CLI.
  **Double-tap guard** in the shared button / form component (ignore taps while
  sending; re-enable on Back), and a friendly "please reload and try again"
  page for CSRF failures instead of a bare 403 (issue #4).
  **From the U0.1 spike review:** no CDN at run time (htmx and CSS served from
  the app); JavaScript in static files, not inline `onsubmit` / `hx-on`, so a
  strict Content Security Policy is possible; an HTMX **timeout** so a hung save
  shows the "not saved" banner and re-enables Save; different wording for "no
  connection" and "server error".
  **From the U0.4a G4 review:** a database `statement_timeout` and
  `idle_in_transaction_session_timeout` (only `lock_timeout` is set), shown
  with the same "Busy, please try again" message.
- **Acceptance:** all components usable one-handed at 375 px width; date and week
  never typed; no UI text hard-coded outside the translation function (checked by
  a lint rule or test).
- **Gate focus:** G5 Staff UAT on the actual lab phones, **including a low-end
  Android** (the vivo Y3s, 3 GB RAM, found the double-tap bug).

### U0.11 · Backup & restore baseline
- **Size:** S · **Deps:** U0.4b
- **Scope:** scheduled DB + file backup to a second location; documented restore.
  The production server is self-hosted, so the second location is **off-site
  cloud storage** (e.g. Cloudflare R2) and must run **before go-live**. The
  off-site copy is encrypted from the start; key management and the rest of
  encryption stay in U6.2. The same restore moves Cucumber to the fallback
  cloud server.
- **Acceptance:** restore of last night's backup into a clean staging host succeeds
  and passes the smoke test **and a post-restore check**: every table in the
  source exists in the restore, row counts per table match, and
  `check_projections` passes (U0.2). The same check is run after any host move;
  the database always moves as one piece (`pg_dump` / `pg_restore`), never
  table by table.
- **Gate focus:** G5 timed restore drill; result logged.
