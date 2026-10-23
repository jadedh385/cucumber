# Shopify integration — architecture decisions

**Date:** 2026-10-23 · **Status:** research only, nothing decided or built · **For:** Owner, to settle before the next stages
**Builds on:** [shopify-research.md](shopify-research.md), [decisions.md](../roadmap/decisions.md), [ADR 0001](../roadmap/adr/0001-stack-selection.md), [U0.2 design](../roadmap/units/u0.2-design.md), [U0.7 design](../roadmap/units/u0.7-design.md)

**Question:** should the Shopify integration sit inside Cucumber's roadmap
phases or come after them, and which design choices would make it a breaking
change if they aren't settled first?

**Short answer:**

- Put Shopify in a **new phase after R1** ("Phase 7 · Sales channels").
- **Five decisions (Part 1) shape Phase 1 units** (U1.3, U1.4, U1.10). Settle
  them, even provisionally, **before U1.3 G0**. These are what would make
  Shopify a breaking change later.
- **Six decisions (Part 2) can wait** for the Shopify phase's G0/G1.

---

## Where Shopify fits in the roadmap

| Option | Trade-off |
|---|---|
| **A. New phase after R1 and U5.2** (recommended) | Builds on real data and calculated availability. Sales today are zero, so nothing forces it earlier. Risk: Phase 1 hard-codes choices that make Shopify awkward later. Part 1 removes that risk. |
| B. Inside Phase 5, next to U5.2 | U5.2 and D-20 are already there. But Phase 5 is analytics. Mixing in a live integration that earns money would hold up R5 and make the phase hard to follow. |
| C. Before R1 | A store could open sooner. But it would sell against data before the 1-week parallel run proves the counts. That is the worst time to oversell. |

The new phase would depend on: R1, U5.2, a new reservations unit (D-20),
U0.11 backups and part of U6.6 (uptime alerts). Today U6.6 sits in Phase 6
with no deadline. Shopify gives it one.

---

## Part 1 · Decide before Phase 1 builds them (expensive to change later)

### 1. What a count means, and what is sold (D-22 + D-23 together)

- **Decision:** what a batch's `live_count` counts (plants, containers or an
  estimate), and how that becomes a number Shopify can sell (single plant,
  bag of 5, jar).
- **Why now:** D-22 is due at U1.3 G0 and D-23 at U5.2 G0. But the sellable
  number pushed to Shopify can only be worked out if every batch at stage ≥ P4
  counts in a unit that converts to packs. U1.10 loads all the V.2 data in
  whatever unit gets chosen. Changing it afterwards means reinterpreting
  migrated history.

| Option | Trade-off |
|---|---|
| **Batches say what they count; sellable stages (≥ P4) always count plants. Packs are a pack size per Shopify variant** (packs available = plants ÷ pack size) | Simple and flexible. A plant can be sold as a single or as a 5-pack from the same stock. Stock shared between pack sizes needs a rule (see 4). |
| Packs become their own batches once bagged | Counts match the shelf exactly. Staff do an extra transfer for every bagging. Unbagged plants can't be sold as packs. |
| One count unit for everything | Easiest to build. Doesn't fit seed, jars or bags of 5 (the D-22 problem). |

**Also decide here:** only the Nursery ships (assumption A3 in the research),
but U5.2's rule doesn't filter by location. Purchased potted plants enter at
**Lab P4** and would be pushed as sellable. Either add "location = Nursery"
to the rule, or map each location to its own Shopify location.

### 2. A sale as its own event

- **Decision:** how "sold and shipped" is recorded. The event `action` check
  in the database (U0.2) has no `sale` action. Only the generic `out` exists.
- **Why now:** U1.4 builds the stock-out flow, and U5.1 metrics need sales
  kept apart from losses. Changing the database check later is a migration
  plus re-labelling every past `out` event.

| Option | Trade-off |
|---|---|
| **New `sale` action with an external reference (channel + order ID), no price** | Clear meaning. The reference makes repeated imports safe and links the sale to its Shopify order. Keeps principle 2 (no money in the app). |
| `out` plus a "sold" reason code | No schema change. Reason codes are meant for voids, corrections and losses, and there's nowhere to keep the order ID. |
| A separate sales table that points at `out` events | Keeps the events table generic. Adds a second write that must stay in step inside the same transaction. |

### 3. What the Shopify link is tied to

- **Decision:** whether the Cucumber ↔ Shopify mapping is keyed on the **SKU
  text** or on the **internal plant ID plus pack size**, and what the Shopify
  variant SKU looks like (for example `PHL001-5`).
- **Why now:** U0.2 Q1 allows a SKU to change when a genus is reclassified. A
  mapping keyed on SKU text breaks silently when that happens. One Cucumber
  SKU will also have several Shopify variants once packs exist (1).

| Option | Trade-off |
|---|---|
| **Mapping table keyed (channel, external ID) → (plant ID, pack size)** | Survives SKU changes and works for later channels. Needs a mismatch check (M3 in the research). |
| Match on SKU text only | No mapping table. Breaks on reclassification and on packs. |

### 4. Reservations (D-20)

- **Decision:** what gets reserved (a quantity or a whole batch), against what
  (plant or pack), from which sources (Zoho pre-orders and Shopify orders),
  and how it is stored.
- **Why now:** D-20 blocks U5.2. Shopify makes it a precondition, because
  without reservations a stock push hands back plants already sold (research
  §1.2). Phase 1 already uses `split` "for a pre-order". If reservations
  become batch splits, that pattern spreads before the decision is made.

| Option | Trade-off |
|---|---|
| **Quantity per plant, in plants, kept in an append-only ledger with a channel and an external reference; the batch is picked at packing time** | Fits Shopify (orders don't name batches). Follows the "events are append-only" rule. Pre-orders and Shopify orders go through one path. |
| Reserve whole batches (a split per order) | Uses what already exists. Every web order means a physical split. Breaks down for single-plant orders. |
| A mutable `reserved_qty` column | Simplest. Loses history and breaks the append-only principle. |

**Also decide:** stock sharing between pack sizes and channels. Either every
channel and pack size sees all sellable plants, or each gets a fixed share.
Plants come in small numbers, so sharing everything risks selling the last
plant twice.

### 5. Who records sales from live selling, direct sales and partners

- **Decision:** which system is the **order hub**. The Owner listed live
  selling on social media and direct and partnership sales as channels, not
  only the Shopify store.
- **Why now:** it decides whether decision 4's ledger needs one source or
  several. It also decides whether Cucumber ever needs order screens.

| Option | Trade-off |
|---|---|
| **Shopify is the order hub: staff enter live, direct and partner sales as Shopify draft orders or through POS** | One import path. Customers stay in Shopify (D-04, PDPA). Draft orders paid by bank transfer or PromptPay carry no Shopify fee. Costs a little staff time per sale. |
| Cucumber is the hub: direct sales are entered in Cucumber, with one adapter per marketplace | Most control. More code, and customer details creep into Cucumber. |
| Mixed (Zoho pre-orders plus Shopify) | Matches today. Two reservation sources to keep in step. |

---

## Part 2 · Decide at the Shopify phase's G0/G1 (cheap to leave until then)

### 6. Background jobs

- **Decision:** what runs polling, pushes, retries and token refresh.
  **Cucumber has no job runner today** (`compose.yaml` has only the database).

| Option | Trade-off |
|---|---|
| **A queue stored in Postgres (Procrastinate or django-q2 with the ORM broker)** | Retries and scheduling, no new service. Fits a single Mac. |
| Management commands on a system timer (launchd / systemd) | Simplest. Retries, overlap guards and visibility are all hand-built. |
| Celery + Redis | The standard choice. Two more services to run, back up and watch on a self-hosted Mac. |

**Also decide:** whether a stock change writes an "outbox" row in the same
transaction as the event (push soon after), or a job recalculates everything
every few minutes. Adding this later is cheap because U0.2 already funnels
every projection change through one function.

### 7. When a count lowers stock below what's reserved

- **Decision:** what happens when a monthly count or a backdated correction
  (up to 7 days, "the count wins") drops sellable stock below reserved stock.
- **Options:** push 0 and flag the orders for staff (safe, may need a
  refund), or let stock go negative and alert (shows the real shortfall but
  needs extra rules). Compare-and-swap stops race conditions, not real
  shortfalls.

### 8. Who integration writes are recorded as

- **Decision:** whose name goes on reservations and mappings written by the
  sync. Today `entered_via` allows only `form` / `assistant`. U0.7 has one
  protected System account, and Undo refuses anything it touched.
- **Options:** the existing System account with `entered_via = 'integration'`
  (no role change, but every integration looks the same), or one service
  account per integration (clearer audit, but touches the U0.6 roles). Also
  decide whether integration writes go through the review queue (D-03).

### 9. Price and accounting

- **Decision:** who owns the retail price, and how online sales reach Zoho
  Books.
- **Options:** **prices kept in Shopify**, which keeps principle 2 intact. For
  accounting: a Shopify → Zoho app, an extension to **Anemone** (it already
  writes to Zoho, D-13), or a monthly manual summary. Cucumber relaying money
  would break principle 2. Depends on Q7 (which Zoho edition).

### 10. Hosting once orders depend on it

- **Decision:** whether the production Mac is reliable enough to earn money.
- **Why:** with polling and compare-and-swap, an outage doesn't oversell.
  Shopify keeps selling against the last numbers and Cucumber catches up. But
  reservations, pushes and packing all stop. ADR 0001's "hassle triggers" for
  moving to the Singapore VPS should be reviewed before the store goes live.
- **Options:** keep the Mac, with U0.11 backups and U6.6 uptime alerts as
  preconditions; or move to the VPS first (about US$6–13 a month, takes the
  Mac out of the picture).
- **Network:** polling only keeps ADR 0001 as it is (no public endpoint).
  Webhooks (N1) need either a narrow Access bypass or Shopify's Pub/Sub or
  EventBridge delivery, which the research hasn't verified.

### 11. Where packing happens, and personal data

- **Decision:** whether staff pack and print labels in the Shopify admin
  (Cucumber only records which batch the plants came from), or in a Cucumber
  packing screen.
- **Trade-off:** a Cucumber screen means one place to work, but it brings
  addresses into Cucumber and widens the PDPA scope (D-04). Working in
  Shopify's admin keeps Cucumber free of customer data, but means two screens
  per order. Basic includes no staff accounts, so this also affects the
  Basic-vs-Grow choice.

---

## Next steps

Turned into roadmap entries, ready to paste, in
[shopify-roadmap-plan.md](shopify-roadmap-plan.md).
