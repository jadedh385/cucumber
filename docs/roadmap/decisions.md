# Decision Register

The SOP ([Plant Inventory V.3 SOP V.2](../../Plant%20Inventory%20V.3%20SOP%20V.2.md))
and the deck (*Plant Inventory Features Overview*, Google Drive) disagree in a
few places, and the SOP has open TBDs. Each item below must be **Resolved**
before the units it blocks can exit **G0**.

**Status:** `Open` → `Proposed` → `Resolved` (record the answer, date, and who decided).

## Conflicts between SOP and deck

| ID | Question | Options | Blocks | Status |
|---|---|---|---|---|
| D-01 | Is this a standalone app or the inventory module of an existing app? Which stack? | **Standalone Cucumber**: Python, Django 5.2 LTS, Django templates + HTMX, PostgreSQL. Hosting and file storage still open. See [ADR-0001](adr/0001-stack-selection.md). | U0.3 and everything after | Resolved |
| D-02 | Tracking grain. SOP: batch is the unit, per-vessel tracking is out of scope. Deck: "vessel health". | **Batch only.** Contamination is handled by **quarantine-by-split**: contaminated vessels move into a child batch flagged `quarantined` (kept and maintained, but isolated); the healthy batch carries on. A quarantined batch is later cleared or closed as lost. U2.6 is **Won't Do**. | U1.3, U1.5, U2.1, U2.6 | Resolved |
| D-03 | Role model. SOP: Owner / Staff. Deck: Read Only / Tech / Supervisor / Admin. | **Admin** = Owner · **Supervisor** = reviews and corrects events, **except their own** (a Supervisor's own events and corrections go to the Owner) · **Tech** = Staff · **Read Only** = view dashboards | U0.6, U1.8 | Resolved |
| D-04 | Contacts. SOP: CRM / customer records out of scope. Deck: vendor **and customer** directory. | **Zoho Books owns vendors.** Cucumber keeps a **read-only copy** of the Zoho vendor list (one-way sync, stores the Zoho contact ID). Staff pick a vendor but cannot create or edit one in Cucumber, so the two lists can't drift. No customers in Cucumber. Gifts use a free-text source note. | U3.2, U3.3 | Resolved |
| D-05 | Data model. SOP §4 says the model is "not fixed yet, pending additional research". | **The [U0.2 spec](units/u0.2-spec.md) and [design note](units/u0.2-design.md)**, with spec questions Q1–Q8 answered (Q1–Q7 2026-10-10, Q8 2026-10-11). Signed off by the Owner 2026-10-11. | U0.2 → all Phase 1 | Resolved |
| D-06 | Acclimatization stages. P3 (Transport) and P4 (Growth maturity) are "reserved"; the deck needs hardening-off batches and greenhouse transfers. | **New stage `A1` Acclimatization**, placed before P4. Ladder: P0 Sterilization → P1 Multiplication → P2 Growth → A1 Acclimatization → P4 Growth maturity (potted). P3, T1, C0 stay reserved. Stages carry an explicit **sort order** (availability uses "stage ≥ P4"), not code order. | U0.9, U2.5, U5.2 | Resolved |
| D-07 | Destructive actions. Events are append-only (SOP); deck requires a justification for destructive actions. Which entities may be deleted or archived at all? | **Nothing hard-deleted.** Data mistakes are fixed with **Void (entered in error)** or **Correction**, always with a reason (dropdown + optional note). Plants and batches can be `Voided` (never existed), separate from `Retired` / `Closed`. Reference items deactivate. **Undo** shortcut for the person who logged an event, for **10 minutes** after saving (a void underneath). Voids go to the review queue (D-03). Real actions done wrongly stay recorded and are fixed forward. Exceptions: anonymise staff personal data on request (PDPA); sandbox data (U6.5) may be wiped. | U0.2, U0.7, U1.8 | Resolved |
| D-08 | Protocol vocabulary. Runner must match *Protocol Tracking System Plan V.1* (stages, media codes). | **Plan shelved.** Cucumber does not align with the Protocol Tracking System Plan. Stage and media vocabulary are owned by Cucumber (U0.9). Protocols (U4.3, U4.4) are still built, with Cucumber's own design, worked out at U4.3's G0. | U4.3, U4.4 | Resolved |
| D-09 | UbiBot access: account, API key, device list, polling vs push. | — | U5.6 | Open |
| D-10 | Network exposure. LAN / VPN only, or public internet? | **Internet-reachable behind an access gate: Cloudflare Tunnel + Access** (email code before anyone reaches Cucumber; no open ports). U6.1 (2FA) and U6.6 (rate limiting) stay in Phase 6. If the app is ever public **without** an access gate, U6.1 and U6.6 move into **R1**. See [ADR-0001](adr/0001-stack-selection.md#network-access-d-10). | R1 release gate | Resolved |
| D-11 | Subculture interval rule: fixed days per stage, per media, or per protocol? | **Default days per stage**; a per-protocol override is added in U4.2. | U2.2, U4.2 | Resolved |
| D-12 | Media reference on events. Today: free `media_code`. After U3.5: link to a prepared-media lot? | **Media code required + optional prepared lot.** | U3.5 | Resolved |

## Added 2026-10-09

| ID | Question | Options | Blocks | Status |
|---|---|---|---|---|
| D-13 | Does **Anemone** (TypeScript app that sends receipts into Zoho Books) stay separate, or move into Cucumber later? | **Keep both apps, linked by IDs.** Anemone writes the `PLT-` ID into the Zoho expense reference field (T-4). Revisit at R1. | Nothing before R1; revisit at R1 | Resolved |
| D-14 | Location names. | **Lab** = old Lab + old Nursery · **Nursery** = old Land. "Land" is no longer a location. | U0.9, U1.3, U1.7, U1.10, U3.1 | Resolved |
| D-15 | Stage rule inside Lab. SOP says Lab batches need a stage, but old Nursery plants (now Lab) are potted plants, not cultures. | ~~Culture / Holding kind~~ dropped: cultures grow into potted plants, so **potted is a stage** (P4 Growth maturity), not a separate batch kind. Lab batches always have a stage; purchased potted plants enter directly at P4. Collection batches at Nursery may leave stage blank (SOP §3). | U0.2, U1.3, U1.7 | Resolved |
| D-16 | UI language. | English now. Every screen's text goes through the translation function from day one so Thai can be added later without touching each screen. | U0.10 | Resolved |
| D-17 | Mobile signal / Wi-Fi at the Nursery (old Land). If unreliable, data entry must work offline and sync later. | **a) Online only.** The Nursery has 24/7 Wi-Fi; each team member's phone hotspot is the backup, for phones and laptops. No offline entry is built. | U0.1, U0.10, U1.7 | Resolved |
| D-18 | Label printing: when labels arrive and how the app reaches the printer. Today labels are typed and printed one by one. | **Concept agreed 2026-10-11:** labels are printed from a Bluetooth printer through its phone app. Cucumber does **not** drive the printer. It lists which labels to print and their exact text, and can export them as a file the printer app may batch-print (see [U4.8 label concept](phase-4-workflow.md#label-concept-d-18)). Hosting no longer depends on this. **Still needed at U4.8 G0:** printer make / model, label size and stock, a sample of today's label, labels per week, who prints and where. Also decide whether U4.8 moves into Phase 1. | U4.5, U4.8 | Open (details at U4.8 G0) |
| D-19 | Plant naming standard. U0.2 Q6 settled duplicates (blocked by any non-voided plant; case, spaces and quote marks ignored) and banned `???` names, but not how names are built. | Open. To decide: species vs cultivar as separate fields (e.g. *Philodendron erubescens* 'Pink Princess'; `sp.` when the species is unknown); a scheme for in-house names when the cultivar is unknown; optional other names (nicknames, Thai name, seller names) and whether search uses them; which name shows where (Zoho, labels, lab screens); format checks (regex) per part. | U1.1 G0, U1.10 (renaming `PHL005`), U4.8 label text | Open |
| D-20 | Pre-orders and reservations. A customer pre-orders plants; staff can split off a batch for the order (U0.2 Q7), but nothing yet stops those plants counting as available to sell. | Open. To decide: reserve a quantity or a whole batch; link to the Zoho sales order (customers stay in Zoho, D-04); available = units − reserved; what happens when the order ships or is cancelled. Becomes a new unit, likely in Phase 5 next to U5.2. | U5.2 availability; new unit | Open |
| D-21 | In-app assistant: an AI helper that advises staff on the right procedure, drafts event entries from plain-language descriptions, and spots problems (e.g. batches empty but open, unusual counts). | Open; revisit after Phase 1 and the review queue are running. **Agreed principle:** the assistant never writes to the database directly; it calls the same services as the screens, as the logged-in user and within that user's role, and **a person confirms before anything is saved**. Events record `entered_via` (`form` / `assistant`) from U0.2 on. To decide: AI provider and cost, Thai support, what it may see (e.g. `zoho_ref` is Admin-only), whether it may draft Voids and Corrections, which phase it belongs in. | Nothing before R1; new unit or phase | Open |

## Open items carried from SOP §9

| ID | Question | Blocks | Status |
|---|---|---|---|
| T-1 | Old `Pipeline` status: map into `Collection`, or add a `Candidate` state? **Add `Candidate`**: Pipeline plants are wanted, not held, so they have no batches or counts. | U1.2, U1.10 | Resolved |
| T-2 | `min_saleable_qty`: per SKU or one global default? **Global default + optional per-SKU override.** | U5.2 | Resolved |
| T-3 | Collection count frequency: monthly or quarterly? **Monthly.** | U1.7 | Resolved |
| T-4 | Zoho link method: reporting tag or reference text? **Reference text** (`PLT-` ID in the expense reference field). | U1.9 | Resolved |
| T-5 | Backfill missing `PHL001/002/003` and 28/01/2026 cohort history, or start V.3 clean? **Start clean** with an opening-balance `Intake` per batch at today's count; V.2 sheets kept read-only; SOP §8 baselines kept as notes. | U1.10 | Resolved |

## Resolution log

| Date | ID | Decision | Decided by |
|---|---|---|---|
| 2026-10-09 | — | App renamed **Cucumber**. "Anemone" is the existing receipts → Zoho Books app (the deck used the name for this app by mistake). | Jade |
| 2026-10-09 | D-14 | Lab = old Lab + old Nursery; Nursery = old Land. | Jade |
| 2026-10-09 | D-16 | English first; translation-ready from day one; Thai in a later phase. | Jade |
| 2026-10-09 | D-01 | Standalone Cucumber on Python + Django 5.2 LTS + HTMX + PostgreSQL. React / Next.js front ends, building inside Anemone, and GraphQL considered and rejected or deferred. Business rules live in services so the front end can be replaced later. [ADR-0001](adr/0001-stack-selection.md). | Jade |
| 2026-10-09 | D-10 | Internet-reachable for remote work and off-site data entry, behind Cloudflare Tunnel + Access. U6.1 and U6.6 stay in Phase 6; they move into R1 only if the access gate is removed. | Jade |
| 2026-10-09 | D-17 | Online only. Nursery has 24/7 Wi-Fi; staff phone hotspots are the backup. | Jade |
| 2026-10-09 | D-03 | Option c: Supervisor may review and correct events except their own; the Owner reviews Supervisor events and corrections. Nobody approves their own work, except the Owner. | Jade |
| 2026-10-09 | D-07 | No hard deletes. Void (entered in error) or Correction with a reason; `Voided` status for plants and batches; 10-minute Undo; voids reviewed; PDPA anonymisation and sandbox wipe are the only exceptions. | Jade |
| 2026-10-10 | D-02 | Batch only. Contamination handled by splitting contaminated vessels into a quarantined child batch. U2.6 Won't Do. | Jade |
| 2026-10-10 | D-04 | Zoho owns vendors; Cucumber keeps a read-only one-way copy (Zoho contact ID). No customers. | Jade |
| 2026-10-10 | D-06 | New stage code for acclimatization (not P4). Code and order pending the Protocol plan (D-08). Stays Proposed. | Jade |
| 2026-10-10 | D-11 | Default subculture interval per stage; per-protocol override in U4.2. | Jade |
| 2026-10-10 | D-12 | Media code required; prepared lot optional. | Jade |
| 2026-10-10 | D-13 | Keep Anemone and Cucumber separate, linked by `PLT-` IDs. Revisit at R1. | Jade |
| 2026-10-10 | D-15 | Culture/Holding kind dropped; potted is a stage. Stays Proposed until the stage ladder is confirmed (D-06 / D-08). | Jade |
| 2026-10-10 | T-1 | New `Candidate` plant status for wanted-but-not-held plants. | Jade |
| 2026-10-10 | T-2 | Global `min_saleable_qty` with optional per-SKU override. | Jade |
| 2026-10-10 | T-3 | Collection counts monthly. | Jade |
| 2026-10-10 | T-4 | Zoho link by reference text. | Jade |
| 2026-10-10 | T-5 | Start V.3 clean with opening-balance Intakes; no backfill. | Jade |
| 2026-10-10 | D-08 | Protocol Tracking System Plan V.1 shelved. Cucumber owns its stage/media vocabulary; protocols still built in Phase 4 with Cucumber's own design. | Jade |
| 2026-10-10 | D-06 | Acclimatization = new stage `A1`, before P4. Explicit stage sort order. | Jade |
| 2026-10-10 | D-15 | Potted = P4. Lab batches always staged; purchased potted plants enter at P4. | Jade |
| 2026-10-11 | D-05 | Data model = U0.2 spec + design note (Q1–Q8 answered). | Jade |
| 2026-10-11 | D-18 | Concept only: no app-to-printer link; Cucumber lists labels and exact text, staff print from the phone app. Details at U4.8 G0. | Jade |
| 2026-10-11 | — | Hosting (first choice, replaced below): cloud VPS in Singapore, with room to move to a lab machine later. File storage: local disk behind django-storages, R2 later. [ADR-0001](adr/0001-stack-selection.md#hosting). | Jade |
| 2026-10-11 | — | Hosting changed: **go live self-hosted**, starting on the Owner's spare MacBook Air M2 (Linux mini PC if it stays); move to the Singapore cloud VPS if any hassle trigger is hit. [ADR-0001](adr/0001-stack-selection.md#hosting). | Jade |
| 2026-10-11 | — | UI kit: **daisyUI 5** (over Basecoat), chosen from the U0.1 spike. [ADR-0001](adr/0001-stack-selection.md#ui-kit). | Jade |
| 2026-10-11 | — | Release notes: one GitHub Release per release with a staff note and a git-cliff technical changelog; date versions `YYYY.MM.N`; when ready, at most weekly; English now, Thai later; publishing posts the staff note to the LINE group. [Release process](release-process.md). | Jade |
