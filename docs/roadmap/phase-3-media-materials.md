# Phase 3 — Media, Materials & Locations

**Goal:** deck section *02*: formulations, prepared media, chemical lots,
suppliers, storage locations. Prices stay in Zoho Books (SOP principle 2).

**Release gate:** [R3](README.md#phase-release-gates)

---

### U3.1 · Storage location hierarchy
- **Size:** M · **Deps:** U0.9, U1.3
- **Source:** deck 02 "Storage Locations"
- **Scope:** Site (Lab / Nursery) → room or area → shelf / chamber / bench / cold
  storage. Batches and material lots can point to a location; searchable.
  The old-Nursery area becomes a named area inside Lab (D-14).
- **Acceptance:** existing Lab / Nursery values become top-level sites;
  moving a batch is a `Transfer` event.
- **Gate focus:** G1 migration of existing location values.

### U3.2 · Supplier & contact directory
- **Size:** S · **Deps:** U0.6 · **Decisions:** D-04
- **Source:** deck 02 "Supplier Contacts"; SOP §1 (no CRM)
- **Scope:** read-only, one-way copy of the **Zoho Books vendor list** (D-04),
  keyed by Zoho contact ID. Staff pick vendors; nobody creates or edits them in
  Cucumber. No customers.
- **Acceptance:** no price or payment fields exist; no create/edit screens for
  vendors; a vendor renamed in Zoho shows the new name after the next sync.
- **Gate focus:** G4 personal data stored only as decided; Zoho API token kept
  out of the code.

### U3.3 · Materials & chemical lots
- **Size:** L · **Deps:** U3.1, U3.2
- **Source:** deck 02 "Materials & Inventory"
- **Scope:** materials catalogue; lots (lot no., supplier, received, expiry,
  quantity, location); lot usage history; expiry status.
- **Acceptance:** expired lots flagged and blocked from new media prep; usage
  can't exceed stock; no cost fields.
- **Gate focus:** G2 expiry and stock-guard tests.

### U3.4 · Media formulation templates
- **Size:** M · **Deps:** U0.9, U3.3
- **Source:** deck 02 "Media Formulations" (tier 1)
- **Scope:** versioned templates for each media code: basal, PGRs, vitamins, other
  components with amounts; target pH. Editing creates a new version.
- **Acceptance:** existing codes `M001–M004, G001, G002, R001` each get a template;
  old versions stay readable.
- **Gate focus:** G5 Owner enters the real recipes.

### U3.5 · Media batch preparation
- **Size:** L · **Deps:** U3.3, U3.4, U1.4 · **Decisions:** D-12
- **Source:** deck 02 "batch preparation logs" (tier 2)
- **Scope:** prep log from a template: volume, lots consumed, measured pH, date,
  staff. Creates a prepared-media lot that subculture events can reference.
- **Acceptance:** lot consumption deducted atomically; pH outside range needs a note;
  traceability from any plant batch → media lot → chemical lots.
- **Gate focus:** G2 end-to-end traceability test.
