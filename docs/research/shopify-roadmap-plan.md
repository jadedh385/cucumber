# Shopify integration — roadmap plan

**Date:** 2026-10-23 · **Status:** proposal; nothing has been added to the roadmap yet · **For:** Owner, to decide what goes into the roadmap
**Builds on:** [shopify-research.md](shopify-research.md) (the research) and [shopify-decisions.md](shopify-decisions.md) (the architecture decisions)

**Question:** which changes from the Shopify work should go into Cucumber's
roadmap, and which of them are still worth making if Shopify is never adopted?

**Short answer:**

- **Seven changes hold whether or not Shopify is adopted** (I1–I7). They fix
  gaps that Zoho pre-orders, direct sales, metrics and the planned Zoho and
  UbiBot syncs already have. Three of them (I1, I3, I4) should be settled
  **before U1.3 G0**, because Phase 1 and the V.2 migration (U1.10) would build
  them into the data.
- **Thirteen items only apply if Shopify is adopted** (S1–S13, section 3).
  They wait for a new Phase 7, after R1. If Shopify is dropped, they are dropped too, and nothing in I1–I7 has to
  change.
- The roadmap entries for I1–I7 are written below in the roadmap's own formats
  (decision rows, unit blocks, tracker rows), ready to paste (section 4).
- **Not added:** no features, services or migration steps beyond what the two
  research documents already name.

**Labels used below**

| Label | Meaning |
|---|---|
| **Independent** | Worth doing even if Shopify is never adopted. Goes into the roadmap now. |
| **Shopify** | Only needed if Shopify is adopted. Dropped if it is not. |

---

## 1. All changes at a glance

| # | Change | Label | Cucumber-wide benefit (without Shopify) | Roadmap entry | Settle by |
|---|---|---|---|---|---|
| I1 | What a count means and what is sold, decided together | Independent | Counts mean the same thing in the lab, metrics, availability and pre-orders. Settled before V.2 data loads, so history never needs reinterpreting. | D-22, D-23 (changed); U1.3 | U1.3 G0 |
| I2 | Sellable stock filtered by location | Independent | Purchased potted plants that enter at Lab P4 stop showing as available for pre-orders and direct sales. | U5.2 (changed) | U5.2 G0 |
| I3 | A sale is its own event | Independent | Metrics (U5.1) can tell sales from losses. Direct and partner sales carry the order reference, and the same sale can't be recorded twice. | D-28 (new); U1.4 | U1.3 G0 |
| I4 | Reservations as an append-only quantity ledger | Independent | Zoho pre-orders stop counting as available. No physical batch split per order. One path for every order source. | D-20 (changed); U5.7 (new) | Decision: U1.3 G0. Unit: after U5.2. |
| I5 | Which system records non-store sales (order hub) | Independent | One answer to where live, direct and partner sales are recorded. It decides whether Cucumber ever needs order screens, and keeps customer data out (D-04). | D-29 (new) | U5.7 G0 |
| I6 | Background jobs | Independent | Scheduled work, retries and overlap guards are built once and reused by the Discord summary (U2.8), the Zoho vendor sync (U3.2) and UbiBot polling (U5.6). | D-30 (new) | First G1 of U2.8, U3.2 or U5.6 |
| I7 | Who integration writes are recorded as | Independent | The Zoho vendor sync and UbiBot readings name a clear actor in the audit trail (U0.7). Undo and review rules for machine writes are set once. | D-31 (new) | First G1 of U3.2 or U5.6 |
| S1 | New Phase 7 · Sales channels, after R1 | Shopify | None. | Phase 7 (new) | When Shopify is adopted |
| S2 | Listing mapping (channel, external ID) → (plant ID, pack size), with a mismatch check | Shopify | None until a second external channel exists. It is channel-neutral, so another channel could reuse it. | Phase 7 | Phase 7 G0 |
| S3 | Stock push with compare-and-swap, idempotency key, Cucumber reference, and an outbox or recalculation job | Shopify | None. | Phase 7 | Phase 7 G1 |
| S4 | Order import by polling (new, cancelled, edited, refunded) | Shopify | None. Its output feeds the I4 ledger. | Phase 7 | Phase 7 G1 |
| S5 | Pack and ship: send the Shopify fulfilment with tracking | Shopify | None. Picking a batch and writing the sale event is part of I4. | Phase 7 | Phase 7 G1 |
| S6 | Sync health page | Shopify | None. | Phase 7 | Phase 7 G1 |
| S7 | App credentials and token refresh | Shopify | None. | Phase 7 | Phase 7 G1 |
| S8 | Shopify writes audited with `via=shopify` | Shopify | None beyond I7. | Phase 7 | Phase 7 G1 |
| S9 | Backups and uptime alerts in place before the store opens; review ADR 0001 hassle triggers | Shopify (timing only) | U0.11 and U6.6 are planned anyway. Only the earlier deadline comes from Shopify. | U0.11, U6.6 (deadline) | Before the store opens |
| S10 | Price owner and how online sales reach Zoho Books | Shopify | None. Principle 2 (no money in the app) already holds. | Phase 7 | Phase 7 G0 |
| S11 | Where packing happens (Shopify admin or Cucumber screen) and the PDPA scope | Shopify | None. | Phase 7 | Phase 7 G0 |
| S12 | Nice-to-haves N1–N6 (webhooks, draft products, Zoho order sync, Discord sell-out alert, per-channel stock split, bulk resync) | Shopify | None. | Phase 7 backlog | Later |
| S13 | Shopify plan and payment provider | Shopify | None (business setup, not code). | Not a unit | Before the store opens |

---

## 2. Independent items

### I1 · What a count means and what is sold (D-22 + D-23)

- **Change:** decide D-22 (what `live_count` counts) and D-23 (selling units)
  together at **U1.3 G0**, instead of D-23 waiting for U5.2 G0. Proposed:
  batches say what they count; sellable stages (≥ P4) always count **plants**;
  a pack is a **pack size per product** (packs available = plants ÷ pack size),
  linked by **plant ID + pack size**, not by SKU text.
- **Why it holds without Shopify:** D-23 already exists for bags of 5, jars and
  cuttings sold through Zoho. U1.10 loads all V.2 data in whatever count unit
  U1.3 picks, so changing the unit later means reinterpreting migrated history.
  SKUs can change when a genus is reclassified (U0.2 Q1), so a link built on
  SKU text breaks for any consumer (Zoho items, labels), not only Shopify.
- **Source:** decisions doc, decisions 1 and 3.

### I2 · Sellable stock filtered by location

- **Change:** at U5.2 G0, settle whether availability counts only the Nursery
  or each location separately.
- **Why it holds without Shopify:** purchased potted plants enter at **Lab P4**
  (D-15), so today's U5.2 rule would show them as sellable for any sale.
- **Source:** decisions doc, decision 1 ("Also decide here").

### I3 · A sale is its own event

- **Change:** add a `sale` event action with an **external reference (channel +
  order ID)** and **no price**. Settle before U1.3 G0 so U1.4 builds it.
- **Why it holds without Shopify:** today only the generic `out` exists, so
  U5.1 can't tell sales from losses. Direct and partner sales need somewhere to
  keep the Zoho sales-order number. Changing the database check after U1.4 is a
  migration plus re-labelling every past `out` event.
- **Source:** decisions doc, decision 2.

### I4 · Reservations as an append-only quantity ledger (D-20)

- **Change:** settle D-20 **before U1.3 G0**. Proposed: reserve a **quantity of
  plants per plant**, in an append-only ledger with a channel and an external
  reference. The batch is picked when the order is packed, which writes the
  `sale` event (I3) and releases the reservation. Available = sellable −
  reserved. Build it as a new unit **U5.7**, next to U5.2.
- **Also part of this decision:**
  - How stock is shared between pack sizes (and, later, channels): all see
    every sellable plant, or each gets a fixed share.
  - What happens when a monthly count or a backdated correction drops sellable
    stock below reserved stock: show 0 and flag the orders, or go negative and
    alert.
- **Why it holds without Shopify:** D-20 exists because Zoho pre-orders don't
  stop plants counting as available. Phase 1 already uses `split` "for a
  pre-order". If that becomes the reservation pattern before D-20 is decided,
  it spreads into Phase 1 screens and the migration.
- **Source:** decisions doc, decisions 4 and 7; research §1.2, §5.

### I5 · Which system records non-store sales (order hub)

- **Change:** decide which system records live, direct and partner sales. If
  Shopify is adopted, the options are Shopify (draft orders or POS), Cucumber,
  or mixed. If it is not, the choice is Cucumber or Zoho.
- **Why it holds without Shopify:** the Owner named these channels whatever
  the storefront. The answer decides how many sources feed I4's ledger and
  whether Cucumber needs order screens, which would bring customer details in
  (D-04, PDPA).
- **Source:** decisions doc, decision 5.

### I6 · Background jobs

- **Change:** choose what runs scheduled and retried work. The options from the
  research: a queue stored in Postgres (Procrastinate or django-q2 with the ORM
  broker), management commands on a system timer, or Celery + Redis. The
  research leans to the Postgres queue (no new service on the Mac).
- **Why it holds without Shopify:** Cucumber has no job runner today
  (`compose.yaml` has only the database). U2.8 (daily Discord summary), U3.2
  (one-way Zoho vendor copy) and U5.6 (UbiBot polling) all need one. Choosing
  once stops each unit building its own timer, retries and overlap guard.
- **Source:** decisions doc, decision 6. The outbox-or-recalculate question
  in the same decision is Shopify-only (S3).

### I7 · Who integration writes are recorded as

- **Change:** decide the actor and `entered_via` value for writes made by a
  sync. Options: the existing System account with `entered_via =
  'integration'`, or one service account per integration (touches U0.6
  roles). Also decide whether these writes go through the review queue (D-03).
- **Why it holds without Shopify:** today `entered_via` allows only `form` /
  `assistant`, and U0.7 has one protected System account that Undo refuses.
  The Zoho vendor copy (U3.2) and UbiBot readings (U5.6) are integration
  writes too.
- **Source:** decisions doc, decision 8.

---

## 3. Shopify-dependent items

These go into a new **Phase 7 · Sales channels** (S1) only if Shopify is
adopted. Placement and reasons: decisions doc, "Where Shopify fits".
Phase 7 depends on R1, U5.2, U5.7 (I4), U0.11 and the uptime part of U6.6.

| # | Item | Research source |
|---|---|---|
| S2 | Listing mapping keyed (channel, external ID) → (plant ID, pack size), with a check that every sellable plant/pack has exactly one listing | Decisions 3; research M3, §5 |
| S3 | Stock push: `inventorySetQuantities` with `changeFromQuantity` (compare-and-swap), idempotency key and `referenceDocumentUri`. Outbox row per stock change, or a recalculation job. | Research §1.2, M4; decisions 6 |
| S4 | Order import by polling, idempotent on Shopify order ID; creates and releases I4 reservations | Research §1.3, M5 |
| S5 | `fulfillmentCreate` with tracking after packing | Research M6 |
| S6 | Sync health page: last push and import, failed items, drift | Research M7 |
| S7 | Dev Dashboard app, secret in `secrets.env` and Bitwarden, token refresh | Research §1.4, M8 |
| S8 | Shopify writes through `audited()` with the I7 actor and `via=shopify` | Research M9 |
| S9 | U0.11 backups and U6.6 uptime alerts done before the store opens; review ADR 0001 hassle triggers (Mac or Singapore VPS) | Decisions 10 |
| S10 | Retail price kept in Shopify (proposed); online sales into Zoho by app, Anemone, or monthly summary | Decisions 9; research §2 |
| S11 | Packing in Shopify admin or a Cucumber screen; affects PDPA scope and Basic vs Grow | Decisions 11 |
| S12 | N1 webhooks, N2 draft products, N3 Zoho order sync, N4 Discord sell-out alert, N5 per-channel stock split, N6 bulk resync | Research §6 |
| S13 | Plan (Basic / Grow) and payment provider(s) | Research §3, §4 |

Phase 7 units are not written out here. Their size and split depend on the
open questions in section 5, which belong at Phase 7 G0.

---

## 4. Roadmap entries (ready to paste)

Formats follow [decisions.md](../roadmap/decisions.md),
[phase-1-core-inventory.md](../roadmap/phase-1-core-inventory.md),
[phase-5-analytics.md](../roadmap/phase-5-analytics.md) and
[tracker.md](../roadmap/tracker.md). The next free IDs are D-28 and U5.7.

### 4.1 `decisions.md` — changed rows (I1, I4)

Replace the D-20, D-22 and D-23 rows with:

```markdown
| D-20 | Pre-orders and reservations. A customer pre-orders plants; staff can split off a batch for the order (U0.2 Q7), but nothing yet stops those plants counting as available to sell. | Open. **Decide before U1.3 G0** (was: with U5.2), so Phase 1 does not spread "split a batch per pre-order". Proposed: reserve a **quantity of plants per plant**, not a batch, in an append-only ledger with a channel and an external reference (the Zoho sales order today; customers stay in Zoho, D-04); the batch is picked when the order is packed, which writes the `sale` event (D-28) and releases the reservation; available = sellable − reserved. Also decide: how stock is shared between pack sizes (D-23); what happens when a count or backdated correction drops sellable below reserved (show 0 and flag the orders, or go negative and alert); what happens when the order is cancelled. Built in **U5.7**. See [Shopify roadmap plan](../research/shopify-roadmap-plan.md#i4--reservations-as-an-append-only-quantity-ledger-d-20). | U1.3 G0, U5.2, U5.7 | Open |
| D-22 | **What a batch's count means.** *(question text unchanged)* | Open. **Decide at U1.3 G0, together with D-23.** *(rest unchanged)* Proposed: batches say what they count; sellable stages (≥ P4) always count plants. | U1.3, U1.4, U1.5, U1.6, U1.7, U1.10, U0.9; feeds D-23, D-24 | Open |
| D-23 | **Selling units.** What is sold is moving beyond one plant: a bag of 5, a single plant, cuttings / pieces, jars. | Open. **Decide at U1.3 G0 with D-22** (was: U5.2 G0), so U1.10 loads data in a unit that converts to packs. Proposed: a pack size per product (packs available = plants ÷ pack size), linked to Zoho items and any later listing by **plant ID + pack size**, not SKU text (SKUs can change, U0.2 Q1). Still to decide: how `min_saleable_qty` (T-2) and reservations (D-20) count, in plants or in packs. | U1.3, U5.2, D-20 | Open |
```

### 4.2 `decisions.md` — new section (I3, I5, I6, I7)

```markdown
## Added 2026-10-23

From the [Shopify roadmap plan](../research/shopify-roadmap-plan.md). Each holds whether or not Shopify is adopted.

| ID | Question | Options | Blocks | Status |
|---|---|---|---|---|
| D-28 | **A sale as its own event.** The event `action` check (U0.2) has no `sale`; only the generic `out` exists, so metrics can't tell sales from losses and there is nowhere to keep an order number. | Open. **Decide before U1.3 G0** so U1.4 builds it. Options: a new `sale` action with an external reference (channel + order ID) and no price (proposed; keeps principle 2); `out` plus a "sold" reason code (no schema change, no place for the order ID); a separate sales table pointing at `out` events (second write kept in step in one transaction). | U1.4, U5.1, U5.7 | Open |
| D-29 | **Order hub.** Which system records sales from live selling on social media, direct sales and partners. | Open. **Decide at U5.7 G0.** Options: Shopify as hub (draft orders or POS), if Shopify is adopted; Cucumber as hub (order screens, customer details creep in, D-04); Zoho as hub (pre-orders as Zoho sales orders, as today); mixed. Decides how many sources feed the reservation ledger (D-20). | U5.7 | Open |
| D-30 | **Background jobs.** Cucumber has no job runner (`compose.yaml` has only the database). | Open. **Decide at the first G1 of U2.8, U3.2 or U5.6.** Options: a queue stored in Postgres (Procrastinate or django-q2 with the ORM broker; no new service); management commands on a system timer (launchd / systemd; retries and overlap guards hand-built); Celery + Redis (two more services on the Mac). | U2.8, U3.2, U5.6 | Open |
| D-31 | **Who integration writes are recorded as.** `entered_via` allows only `form` / `assistant`; U0.7 has one protected System account that Undo refuses. | Open. **Decide at the first G1 of U3.2 or U5.6.** Options: the System account with `entered_via = 'integration'` (no role change, every integration looks the same); one service account per integration (clearer audit, touches U0.6 roles). Also decide whether integration writes go through the review queue (D-03). | U3.2, U5.6 | Open |
```

### 4.3 `phase-1-core-inventory.md` — changed lines (I1, I3, I4)

U1.3, replace the Size line:

```markdown
- **Size:** M · **Deps:** U1.1 · **Decisions:** D-02, D-14, D-15, **D-22 and D-23 (decided here, at G0)**; D-20 and D-28 settled before G0
```

U1.4, replace the Size line and the Scope line:

```markdown
- **Size:** L · **Deps:** U1.3, U0.7 · **Decisions:** D-28
- **Scope:** log `Intake`, `Count`, `Contamination`, `Out`, `Sale` (D-28), `Loss` (SOP-11), `Correction`.
```

### 4.4 `phase-5-analytics.md` — U5.2 changed, U5.7 new (I2, I4, I5)

U5.2, add after the Scope paragraph:

```markdown
- **G0 to settle:** which locations count as sellable. Purchased potted plants
  enter at Lab P4 (D-15), so either filter to `Nursery` or count each location
  separately. Units are counted as decided by D-22 / D-23 at U1.3.
```

New unit, after U5.6:

```markdown
### U5.7 · Reservations
- **Size:** M · **Deps:** U5.2, U1.4 · **Decisions:** D-20, D-23, D-28, **D-29 (decided here, at G0)**
- **Source:** D-20; [Shopify roadmap plan](../research/shopify-roadmap-plan.md) I4
- **Scope:** append-only reservation ledger: a quantity of plants per plant,
  with a channel and an external reference (Zoho sales order today). Available
  = sellable − reserved. Packing picks the batch, writes the `sale` event and
  releases the reservation; cancelling releases it without a sale. A count or
  correction that drops sellable below reserved is handled as D-20 decides.
- **Acceptance:** reservations are never edited, only added or released;
  availability changes as soon as a reservation is added or released; the same
  external reference can't reserve twice; no customer data stored (D-04).
- **Gate focus:** G2 property-based test: available = sellable − open
  reservations for random sequences · G5 Owner reserves and ships a real
  pre-order.
```

### 4.5 `tracker.md` — changed and new rows

```markdown
| U1.3 | Batches | M | D-02, D-15, D-20, D-22, D-23, D-28 | · | · | · | · | · | · | · |
| U1.4 | Events & live counts | L | D-28 | · | · | · | · | · | · | · |
| U5.2 | Availability calculation | S | T-2, D-06, D-23 | · | · | · | · | · | · | · |
| U5.7 | Reservations | M | D-20, D-29 | · | · | · | · | · | · | · |
```

U2.8, U3.2 and U5.6 each gain **D-30**; U3.2 and U5.6 also gain **D-31** in
their "Blocked by" cell. The [roadmap README](../roadmap/README.md) unit count
goes from 52 to 53, and the Phase 5 row from U5.1–U5.6 to U5.1–U5.7.

### 4.6 Only if Shopify is adopted

- Add **Phase 7 · Sales channels** to the README's phase table and sequencing
  diagram (after R1, U5.2 and U5.7), with S2–S12 as its units, written at
  Phase 7 G0.
- Give U0.11 and the uptime part of U6.6 a deadline: before the store opens
  (S9).

---

## 5. Open questions

Merged from both research documents. Questions already answered by the Owner
on 2026-10-22 are not repeated (see the research, section 0).

**Owner** = Jade. **Claude** = research or verification in a later session.

### Needed before U1.3 G0 (independent)

| # | Question | From | Owner | Next step |
|---|---|---|---|---|
| O1 | What a count means at each stage, and the pack sizes per product (D-22, D-23; Q3: how many sellable SKUs, in what units) | Research Q3; decisions 1 | Owner | Answer at U1.3 G0, with a list of today's selling units |
| O2 | Reserve a quantity or a batch; stock sharing between pack sizes; count falls below reserved (D-20) | Decisions 4, 7 | Owner | Answer before U1.3 G0 |
| O3 | `sale` action vs `out` + reason vs sales table (D-28) | Decisions 2 | Owner | Answer before U1.3 G0 |

### Needed later in the roadmap (independent)

| # | Question | From | Owner | Next step |
|---|---|---|---|---|
| O4 | Which locations count as sellable | Decisions 1 | Owner | Answer at U5.2 G0 |
| O5 | Order hub for live, direct and partner sales (D-29) | Decisions 5 | Owner | Answer at U5.7 G0 |
| O6 | Background job runner (D-30) | Decisions 6 | Owner, on Claude's comparison | Compare at the first G1 of U2.8 / U3.2 / U5.6 |
| O7 | Integration actor and review of machine writes (D-31) | Decisions 8 | Owner | Answer at the first G1 of U3.2 / U5.6 |

### Needed only if Shopify is adopted (Phase 7 G0)

| # | Question | From | Owner | Next step |
|---|---|---|---|---|
| O8 | Adopt Shopify at all, and when (after R1) | Decisions, "Where Shopify fits" | Owner | Decide after R1 |
| O9 | New or existing store; plan (Basic or Grow), and what "staff accounts not included" on Basic means in practice | Research Q1, §4 | Owner; Claude checks the staff-account rule | Check Shopify's plan page, then decide |
| O10 | Average order value (THB) | Research Q2 | Owner | Estimate; it sets when Grow beats Basic |
| O11 | Is there a selling entity in a Shopify Payments country? Is the business VAT-registered? | Research Q5 | Owner | Answer; with an accountant if needed |
| O12 | Export currencies and plant export permits for USA, EU / UK, Asia | Research Q6 | Owner | Answer; permits are outside the research so far |
| O13 | Zoho Books edition, and how online orders should land in Zoho | Research Q7; decisions 9 | Owner | Check the Zoho account |
| O14 | Owner's payment methods (PayPal, bank transfer, Wise, Revolut) vs the research recommendation (one Thai provider for cards and PromptPay). Wise and Revolut as Shopify payment methods were not researched. | Research §0, §3 | Claude, then Owner | Research Wise / Revolut in Shopify checkout, then Owner chooses |
| O15 | Which Thai providers actually appear in the store's Payments page, and their written rates | Research §3 | Owner | Check the store admin; ask providers for written rates |
| O16 | Thai VAT on Shopify's fees | Research §4 | Accountant (via Owner) | Ask |
| O17 | Does Shopify Shipping work in Thailand, or do we need a courier app? | Research §2 | Claude | Verify in Shopify docs |
| O18 | Do Dev Dashboard app tokens expire after 24 hours? | Research §1.4 | Claude | Verify in Shopify docs |
| O19 | Can webhooks go to Pub/Sub or EventBridge, avoiding a public path? | Research §1.3 | Claude | Verify; only matters for N1 |
| O20 | Is the 3-option limit per product real? | Research §1.4 | Claude | Verify in Shopify docs |
| O21 | Which setting stops selling at zero stock | Research §2 | Claude | Verify in Shopify docs |
| O22 | Price owner: Shopify, Zoho or Cucumber | Research §1.1; decisions 9 | Owner | Answer; research proposes Shopify |
| O23 | Pack in Shopify admin or a Cucumber screen | Decisions 11 | Owner | Answer; affects PDPA and Basic vs Grow |
| O24 | Keep the production Mac or move to the Singapore VPS before the store opens | Decisions 10 | Owner | Review ADR 0001 hassle triggers |
| O25 | Hub for marketplaces: Cucumber adapters or Shopify's connector; Lazada, Shopee and LINE APIs not researched | Research §5 | Owner; Claude researches if needed | Only once a marketplace is wanted |

---

## 6. What changed in `docs/research`

| Before | After | Why |
|---|---|---|
| `shopify-integration.md` | `shopify-research.md` | One naming pattern: `shopify-<kind>.md` |
| `shopify-architecture-decisions.md` | `shopify-decisions.md` | Same |
| `shopify-integration-follow-up-prompt.md` | Deleted | Empty file (0 bytes); nothing lost |
| — | `shopify-roadmap-plan.md` | This plan |

Inside the files:

- **Research, section 0:** the "Still open" table now has a Status column that
  marks what the Owner answered on 2026-10-22, instead of listing answered
  questions as open next to the answers. It links here for the merged list.
- **Decisions, "Next steps":** replaced by a link to section 4, which turns
  those steps into ready-to-paste entries. One change from the old list:
  decision 3 (the listing mapping) is not a new D-item. Its Shopify part is S2,
  and the part that holds without Shopify (link by plant ID + pack size, not
  SKU text) is folded into D-23.
- **Decisions, "Builds on":** link updated to the new research file name.

No findings were removed. The two documents overlap on purpose. The research
gives facts and options; the decisions doc picks which options must be settled
first.
