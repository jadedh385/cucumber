# Phase 1 — Core Inventory (MVP)

**Goal:** implement SOP-1 to SOP-8 so V.3 fully replaces the V.2 Google Sheets.
This is the MVP. Deck section: *01 Core Lab Management* (registry, lines,
subculture) — depth features follow in Phase 2.

**Release gate:** [R1](README.md#phase-release-gates)

---

### U1.1 · Plant registry (mother plant inventory)
- **Size:** M · **Deps:** U0.7, U0.8, U0.9, U0.10
- **Source:** SOP-1, SOP §3 sources; deck 01 "Mother Plant Inventory"
- **Scope:** create / view / search plants: genus, full name, source, notes,
  acquisition date. Duplicate check (genus + name) before create. New plants
  start as `Collection`.
- **Acceptance:** search shows likely duplicates before save; `PLT-` ID assigned;
  unidentified plants (e.g. `PHL005` "Philodendron ???") are valid.
- **Gate focus:** G2 fuzzy duplicate tests · G5 Owner registers 5 real plants.

### U1.2 · Plant status & SKU promotion
- **Size:** S · **Deps:** U1.1, U0.6 · **Decisions:** T-1
- **Source:** SOP-2, SOP §5 rules 1–2
- **Scope:** Owner-only promote / demote / retire. Promote proposes next SKU for
  the genus; stamps `promoted_by` / `promoted_at`.
- **Acceptance:** SKU only set when `Portfolio`; unique; genus prefix matches;
  non-Owner gets 403; demote keeps SKU history in audit.
- **Gate focus:** G2 rule-1 and rule-2 tests per role.

### U1.3 · Batches
- **Size:** M · **Deps:** U1.1 · **Decisions:** D-02, D-14, D-15
- **Source:** SOP §4 `batches`, SOP-3
- **Scope:** `Culture` batches (tissue culture, stage required) and `Holding`
  batches (potted / standing stock, one per plant per location, stage optional),
  in `Lab` or `Nursery`. Optional `parent_batch_id`. Batch closes when count hits 0
  or by Owner with reason. Display `<SKU or PLT> · Bnnn`.
- **Acceptance:** Culture batch requires a stage; Holding batch may omit it;
  only one open Holding batch per plant per location.
- **Gate focus:** G1 display-ID rule documented · G2 uniqueness tests.

### U1.4 · Event logging & live counts
- **Size:** L · **Deps:** U1.3, U0.7
- **Source:** SOP §4 `events`, §5 rules 5–7, principle 5
- **Scope:** log `Intake`, `Count`, `Contamination`, `Out`, `Loss` (SOP-11), `Correction`.
  `live_count` and `week` always calculated. Unreviewed events flagged.
- **Acceptance:** event that would make `live_count < 0` is rejected with a clear
  message; events can't be edited; `Correction` adjusts totals; week derived
  from `occurred_at`.
- **Gate focus:** G2 property-based test: count = sum of events for random
  sequences · G4 DB review on the count query · G5 10× volume timing.

### U1.5 · Subculture & branching
- **Size:** M · **Deps:** U1.4
- **Source:** SOP-4, rule 4; deck 01 "Subculture & Branching"
- **Scope:** one form: pick parent, units used, number of child batches, media
  code, stage, contaminated thrown away, contaminated kept. Creates children with
  `parent_batch_id` and `Intake` on each, in **one transaction**; contamination
  and quarantine are written as separate operations (U0.2 Q4).
- **Acceptance:** all-or-nothing (a failure creates no partial children);
  contaminated units leave the parent; parent can't go negative.
- **Gate focus:** G2 transaction-rollback test · G5 Staff runs a real
  subculture session with the phone.

### U1.6 · Stage change & transfer
- **Size:** M · **Deps:** U1.4
- **Source:** SOP-5
- **Scope:** `StageChange` (e.g. P1 → P2) and `Transfer` between locations;
  transfer moves units out of one batch and into the destination batch
  (create or add) atomically.
- **Acceptance:** reserved stages are hidden until enabled; transfer conserves
  units (out = in).
- **Gate focus:** G2 conservation test.

### U1.7 · Collection counts
- **Size:** S · **Deps:** U1.4 · **Decisions:** T-3, D-15, D-17
- **Source:** SOP-6
- **Scope:** count sheet listing Collection plants in Holding batches, grouped by
  location (Lab, Nursery); enter physical quantity; app stores the difference
  from the last count.
- **Acceptance:** difference shown before save; overdue counts listed per the T-3 cadence.
- **Gate focus:** G5 Staff completes a full count walk at the nursery.

### U1.8 · Review queue & corrections
- **Size:** M · **Deps:** U1.4, U0.6
- **Source:** SOP-7, rule 7
- **Scope:** queue of unreviewed events **and voids** (D-07), filters by week /
  staff / batch; mark reviewed (single + bulk); add `Correction` from the queue.
- **Acceptance:** reviewed events stamp `reviewed_by` / `reviewed_at`; only Admin
  and Supervisor can review (D-03); a Supervisor's own events and corrections
  appear only in the Owner's queue and can't be reviewed by that Supervisor;
  unreviewed events still count toward totals.
- **Gate focus:** G5 Owner does a weekly review on a week of real data.

### U1.9 · Zoho Books reference link
- **Size:** S · **Deps:** U1.1 · **Decisions:** T-4
- **Source:** SOP-8, rule 3, principle 2
- **Scope:** store `zoho_ref` on plants with `source = Purchase`; Owner-only visibility.
  **No amounts stored.**
- **Acceptance:** Purchase without vendor or `zoho_ref` is accepted and listed on
  "Zoho link missing"; promotion to Portfolio is refused until both are set
  (U0.2 Q2); non-Owner never sees `zoho_ref` in UI or API.
- **G0 to settle:** convention when one Zoho expense covers several plants
  (several `PLT-` IDs in the reference field, or one per line item).
- **Gate focus:** G4 security review on field-level permission.

### U1.10 · V.2 data migration
- **Size:** L · **Deps:** U1.1–U1.9 · **Decisions:** T-1, T-5
- **Source:** SOP §1 "Why V.3", §9 migration prerequisite, §10 sources
- **Scope:** import Product Acquisition, Product Plants, Plant Inventory V.2;
  map statuses; rebuild batches; generate opening `Intake` events; old land and
  nursery stock (≈ 47 Hoya) included. Map V.2 locations per D-14:
  `Nursery` → `Lab`, `Land` → `Nursery`.
- **Acceptance:** reconciliation report: every V.2 row is imported, merged, or
  rejected with a reason; counts per SKU match V.2 totals.
- **Gate focus:** G2 dry-run on a copy, idempotent re-run · G5 Owner signs the
  reconciliation report · G6 V.2 sheets set read-only.
