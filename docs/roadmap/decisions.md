# Decision Register

The SOP ([Plant Inventory V.3 SOP V.1](../../Plant%20Inventory%20V.3%20SOP%20V.1.md))
and the deck (*Plant Inventory Features Overview*, Google Drive) disagree in a
few places, and the SOP has open TBDs. Each item below must be **Resolved**
before the units it blocks can exit **G0**.

**Status:** `Open` → `Proposed` → `Resolved` (record the answer, date, and who decided).

## Conflicts between SOP and deck

| ID | Question | Options | Blocks | Status |
|---|---|---|---|---|
| D-01 | Is this a standalone app or the inventory module of an existing app? Which stack? | Proposed: standalone app **Cucumber**, built from scratch in Python (Django + PostgreSQL + HTMX), structured as modules so other business functions can join later. Alternative still under review: build inside Anemone (TypeScript). | U0.3 and everything after | Proposed |
| D-02 | Tracking grain. SOP: batch is the unit, per-vessel tracking is out of scope. Deck: "vessel health". | a) Batch only; vessel health recorded as batch-level notes and counts · b) Add vessel tracking later (U2.6) | U1.3, U2.6 | Open |
| D-03 | Role model. SOP: Owner / Staff. Deck: Read Only / Tech / Supervisor / Admin. | Proposed mapping: Admin = Owner, Supervisor = may review events, Tech = Staff, Read Only = view dashboards | U0.6 | Proposed |
| D-04 | Contacts. SOP: CRM / customer records out of scope. Deck: vendor **and customer** directory. | a) Vendors only · b) Vendors + minimal customer names (no CRM data) | U3.2 | Open |
| D-05 | Data model. SOP §4 says the model is "not fixed yet, pending additional research". | Finalize in U0.2 | U0.2 → all Phase 1 | Open |
| D-06 | Acclimatization stages. P3 (Transport) and P4 (Growth maturity) are "reserved"; the deck needs hardening-off batches and greenhouse transfers. | a) Use P4 for acclimatization · b) Add a new stage code (needs agreement with Protocol Tracking plan) | U2.5, U5.2 | Open |
| D-07 | Destructive actions. Events are append-only (SOP); deck requires a justification for destructive actions. Which entities may be deleted or archived at all? | Proposed: nothing hard-deleted; plants retire, batches close, reference items deactivate; each needs a reason | U0.7 | Proposed |
| D-08 | Protocol vocabulary. Runner must match *Protocol Tracking System Plan V.1* (stages, media codes). | Read and align the plan in U4.3/G0 | U4.3, U4.4 | Open |
| D-09 | UbiBot access: account, API key, device list, polling vs push. | — | U5.6 | Open |
| D-10 | Network exposure. LAN / VPN only, or public internet? | If public: move U6.1 (2FA) and U6.6 (rate limiting) into **R1** | R1 release gate | Open |
| D-11 | Subculture interval rule: fixed days per stage, per media, or per protocol? | — | U2.2, U4.2 | Open |
| D-12 | Media reference on events. Today: free `media_code`. After U3.5: link to a prepared-media lot? | a) Keep code + optional lot · b) Lot required | U3.5 | Open |

## Added 2026-10-09

| ID | Question | Options | Blocks | Status |
|---|---|---|---|---|
| D-13 | Does **Anemone** (TypeScript app that sends receipts into Zoho Books) stay separate, or move into Cucumber later? | a) Keep both apps, link them by IDs (e.g. `PLT-` on expenses) · b) Move Anemone into Cucumber as a module · c) Build Cucumber inside Anemone instead (reopens D-01) | Nothing before R1 if D-01 = Python standalone; revisit at R1 | Open |
| D-14 | Location names. | **Lab** = old Lab + old Nursery · **Nursery** = old Land. "Land" is no longer a location. | U0.9, U1.3, U1.7, U1.10, U3.1 | Resolved |
| D-15 | Stage rule inside Lab. SOP says Lab batches need a stage, but old Nursery plants (now Lab) are potted plants, not cultures. | Proposed: batch has a **kind**: `Culture` (stage required) or `Holding` (potted / standing stock, stage optional). Holding batches can sit in Lab or Nursery. | U0.2, U1.3, U1.7 | Proposed |
| D-16 | UI language. | English now. Every screen's text goes through the translation function from day one so Thai can be added later without touching each screen. | U0.10 | Resolved |
| D-17 | Mobile signal / Wi-Fi at the Nursery (old Land). If unreliable, data entry must work offline and sync later. | a) Reliable → online only · b) Unreliable → offline entry (adds a unit, harder build) | U0.1, U0.10, U1.7 | Open |

## Open items carried from SOP §9

| ID | Question | Blocks | Status |
|---|---|---|---|
| T-1 | Old `Pipeline` status: map into `Collection`, or add a `Candidate` state? | U1.2, U1.10 | Open |
| T-2 | `min_saleable_qty`: per SKU or one global default? | U5.2 | Open |
| T-3 | Collection count frequency: monthly or quarterly? | U1.7 | Open |
| T-4 | Zoho link method: reporting tag or reference text? | U1.9 | Open |
| T-5 | Backfill missing `PHL001/002/003` and 28/01/2026 cohort history, or start V.3 clean? | U1.10 | Open |

## Resolution log

| Date | ID | Decision | Decided by |
|---|---|---|---|
| 2026-10-09 | — | App renamed **Cucumber**. "Anemone" is the existing receipts → Zoho Books app (the deck used the name for this app by mistake). | Jade |
| 2026-10-09 | D-14 | Lab = old Lab + old Nursery; Nursery = old Land. | Jade |
| 2026-10-09 | D-16 | English first; translation-ready from day one; Thai in a later phase. | Jade |
