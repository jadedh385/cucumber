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

- **Decision:** what a batch's `live_count` counts (plants, vessels or an
  amount of material), and how that becomes a number Shopify can sell. The
  Owner sells, or expects to sell, four kinds of unit: **single plants**,
  **bags of 3 and 5**, **whole vessels** (a flask or jar, including ones
  whose contents can't be counted) and **cuttings, pieces or seed by weight**.
- **Why now:** D-22 is due at U1.3 G0 and D-23 at U5.2 G0. But the sellable
  number pushed to Shopify can only be worked out if every sellable batch
  counts in a unit that converts to what is sold. U1.10 loads all the V.2 data
  in whatever unit gets chosen. Changing it afterwards means reinterpreting
  migrated history.

| Option | Trade-off |
|---|---|
| **Each batch says what it counts (plant, vessel or weight). Each selling unit names the count unit it draws on and how many it takes. Bags are made up at packing, not kept as batches** (bags available = plants ÷ bag size) | Fits all four selling units, including flasks of uncountable callus. A plant can be sold as a single, a bag of 3 or a bag of 5 from the same stock. Stock shared between selling units needs a rule (see 4). Adds three columns to `batches` (1a) and one small table of selling units (1d). |
| Bags become their own batches once bagged | Counts match the shelf exactly. Staff do an extra transfer for every bagging. Unbagged plants can't be sold as bags. Doesn't help with flasks or seed. |
| Sellable stages (≥ P4) always count plants; everything earlier counts vessels | Close to today. Can't sell a flask or seed, because those are never at P4. |
| One count unit for everything | Easiest to build. Doesn't fit seed, jars or bags of 5 (the D-22 problem). |

The rest of this section spells out the recommended option as a **counting
convention**. It is a starting point for D-22 and D-23, not a settled design.
Cucumber's designs can still change. The parts that are costly to change once
U1.10 has loaded data are the three count units (1a) and the rule that a unit
only changes when stock moves into a new batch (1c).

#### 1a · What a count refers to

Four things get counted, or hold a count. Only the first three are **count
units**, meaning the thing `live_count` is a number of:

| Term | What it is | Is it a count unit? |
|---|---|---|
| **Plant** | One individual you can pick up and separate: a rooted plantlet, a deflasked seedling, a potted plant, a cutting once taken. | Yes: `plant` |
| **Vessel** | One container counted as a whole: flask, jar, tube, magenta box, cup, culture bag. Its contents may be countable (about 20 plantlets) or not (callus, protocorms, a clump, sown seed). | Yes: `vessel` |
| **Weight** | An amount of material too small or numerous to count, mainly seed. Recorded in whole milligrams so `live_count` stays a whole number (rule 7). | Yes: `mg` |
| **Batch** | The group tracked together (D-02). It **holds** a count. It is never what gets counted. | No |

Each batch has three fields (D-22's "column or two", carried by U1.3):

- `count_unit`: `plant`, `vessel` or `mg`. Required, and fixed for the
  batch's whole life.
- `container_type`: picked from a reference list (U0.9), for example "250 ml
  flask", "magenta box", "4-inch pot" or "grow bag".
- `est_plants_per_vessel`: optional, for vessel batches only. It's an
  **estimate**, used for labels and listing text ("about 20 seedlings"). It is
  never added up as stock, never decremented and never pushed to Shopify.

#### 1b · Units by stage

This is how labs in the industry usually count. Cultures are counted by the
vessel while they multiply, because a clump or callus can't be split into
plants. They switch to counting plants at deflasking, where each plantlet is
handled one by one.

| Stage | What is on the shelf | Usual count unit |
|---|---|---|
| `P0` Sterilization / introduction | Explants in tubes or jars | `vessel` |
| `P1` Multiplication | Clumps, callus or protocorms in jars, flasks or magenta boxes | `vessel` (uncountable contents) |
| `P2` Growth | Separate shoots and rooting plantlets, still in vessels | `vessel`, with an estimated number of plants per vessel |
| `A1` Acclimatization | Deflasked plantlets in trays or cups | `plant` |
| `P4` Potted | Pots, bags | `plant` |
| Nursery, no stage | Collection plants in pots | `plant` |
| Seed (any stage) | Seed packets, or seed sown in a box | `mg` until sown, then `vessel` |
| Mother stock for cuttings | Potted mother plants | `plant` (the mothers themselves) |

This table is a guide. The batch's own `count_unit` is what counts. A P2 batch
of large single plantlets in cups can count `plant`.

#### 1c · Where the unit changes

A batch keeps one count unit. The unit changes only when stock moves into a
**new child batch**, through events that already exist (subculture, transfer,
split). Both sides of the move are recorded in their own units in one
operation, as U0.2b already does for subculture (units used on the parent,
units made on each child).

| Point | Parent side (out) | Child side (in) | Example |
|---|---|---|---|
| Subculture | vessels | vessels | 5 jars → 55 jars (the V.2 `PHL001` baseline) |
| Deflasking / prick-out | vessels | plants | 3 magenta boxes → 135 plantlets |
| Sowing | mg | vessels | 200 mg *Drosera* seed → 4 boxes |
| Taking cuttings | none (the mother plant stays) | plants | 1 mother → 12 cuttings |
| **Bagging into 3s or 5s** | **No unit change.** Bags aren't batches (1e). | | |

The ratio between the two sides is a fact recorded on the event, not a fixed
conversion. That is how contamination, losses and the multiplication factor
(D-24) can be read across units without guessing.

#### 1d · Selling units and their conversion

A **selling unit** is one way of selling a plant. Each one becomes a Shopify
variant. It has three parts: the plant (its SKU), the count unit it draws
on, and the **quantity per selling unit**.

```
base units (plant, count unit) = sum of live_count over the plant's open,
                                 non-quarantined batches with that count_unit,
                                 at the selling unit's eligible stages
                                 (and location, see the location note below)
available (selling unit)       = floor((base units − reserved base units)
                                       ÷ quantity per selling unit)
```

- **Plant units** (single, bag of 3, bag of 5) share one pool of plants.
  Selling a bag of 5 lowers what the single and the bag of 3 can show.
  Shopify keeps a separate stock number for each variant, so Cucumber
  recalculates and pushes **every** variant of a plant after any change.
- **Vessel units** draw on vessels. Selling a flask removes 1 vessel. The
  estimated plants inside are never counted, so selling a flask of callus
  works the same way as a flask of 20 seedlings.
- **Weight units** draw on milligrams. A 1 g packet removes 1,000 mg.
- **Eligible stages belong to each selling unit**, not to the plant. Plant
  units default to stage ≥ P4 (as in SOP §8). Vessel units need their own
  list, for example P2 only, because a flask is never at P4.
- **`min_saleable_qty` (T-2)** is checked in base units, before dividing.
  So a threshold of 10 on plant stock means no singles, 3s or 5s go on sale
  until 10 sellable plants exist.
- **Variant SKUs** follow decision 3's example: the Cucumber SKU plus a
  suffix. A plain number means plants: `PHL001-1`, `PHL001-3`, `PHL001-5`.
  A letter means another unit: `PHL001-V` (one vessel) and `DRS001-W1000`
  (1,000 mg). The suffix is only a label. The link itself stays keyed on
  plant ID and selling unit (decision 3), so a reclassification that
  changes the SKU doesn't break it.

#### 1e · When stock goes down

**Reserve at order, deduct at packing.** This matches decision 4.

1. **Order or reservation.** A reservation of *quantity × quantity per
   selling unit* base units goes into the reservation ledger (decision 4).
   A bag of 5 reserves 5 plants. A flask reserves 1 vessel. No batch is
   chosen yet, and `live_count` doesn't change. The Shopify number for
   every variant of that plant drops straight away.
2. **Packing.** Staff pick the batch or batches and make up the unit. The
   sale event (decision 2) takes the stock out of each batch, in that
   batch's count unit, with the order reference. A bag of 5 drawn from two
   batches writes two events with the same reference. The reservation is
   then marked fulfilled.
3. **Record what physically leaves.** If staff add a bonus plant to a bag
   of 5 (a common habit, to cover a death in transit), the events record 6
   plants out. The extra plant isn't hidden in the pack size.

Bags made up ahead of time, for example for a live-selling session, still
belong to their batch until sold. At a monthly count, a bagged plant counts
as a plant in its batch.

#### 1f · How the current SKU designs map

There's no product list yet (research Q3 is still open). The rows below are
the SKU format and the selling-unit examples already in this document, the
SOP and the decisions log.

| Design | Count unit | Quantity per unit | Maps cleanly? |
|---|---|---|---|
| Cucumber SKU `PHL001` (one per cultivar, SOP §5 rule 1) | n/a. It names the plant, not a unit. | n/a | ✅ One SKU, many selling units |
| Single plant, `PHL001-1` | `plant` | 1 | ✅ |
| Bag of 3, `PHL001-3` | `plant` | 3 | ✅ Shares the plant pool |
| Bag of 5, `PHL001-5` (decision 3's example) | `plant` | 5 | ✅ Shares the plant pool |
| Jar or flask, countable plantlets, `PHL001-V` | `vessel` | 1 | ⚠️ Never reaches P4, so it needs its own eligible stages, and is it sold from the Lab? |
| Flask of callus, protocorms or sown seed | `vessel` | 1 | ⚠️ Same as above. Listing text can't promise a plant count. |
| Seed by weight, `DRS001-W1000` | `mg` | for example 1,000 | ⚠️ Needs a scale and whole-milligram entry. Seed sold by count instead would be `plant`. |
| Cuttings or pieces | `plant`, in a cuttings batch | 1 or *n* | ⚠️ Taking cuttings doesn't reduce the mother, so stock exists only once cuttings are logged as a new batch (1c). Cuttings taken to order need a decision. |
| Purchased potted plant at **Lab P4** | `plant` | 1 | ⚠️ The location gap below |
| V.2 counts, for example `PHL001` 5 → 55 | Unknown | n/a | ⚠️ V.2 doesn't say if 55 means jars or plantlets. U1.10 must give every migrated batch a `count_unit`. |

**Location (also decide here):** only the Nursery ships (assumption A3 in the
research), but U5.2's rule doesn't filter by location. Purchased potted plants
enter at **Lab P4** and would be pushed as sellable. Either add "location =
Nursery" to the rule, or map each location to its own Shopify location. Flask
sales make this harder, because flasks live in the Lab.

#### 1g · Knock-on effects on other decisions

These don't change sections 2–11. They are what those sections mean under
this convention:

- Decision 3's "pack size" means a **selling unit** (count unit plus quantity).
- Decision 4's "in plants" means **in the selling unit's count unit**: plants,
  vessels or milligrams.
- D-24's multiplication factor has to be measured in one count unit every
  time. Section 1c gives the vessel-to-vessel ratio it needs.

#### 1h · Open points for the Owner

| # | Question |
|---|---|
| 1.1 | For each V.2 batch, what did the number count? Jars or plantlets? (Needed at U1.10.) |
| 1.2 | Which stages and locations may sell flasks? Is there a promised minimum of plantlets per flask? |
| 1.3 | Cuttings: are they always logged as a batch before sale, or cut to order? |
| 1.4 | Seed: sold by weight, by count, or as a packet of a fixed size? |
| 1.5 | Should a minimum number of plants be held back for each selling unit, or only one shared `min_saleable_qty`? |
| 1.6 | Which stage does a seed lot in the Lab have? Every Lab batch needs one (SOP rule 6), but seed counted in `mg` isn't really `P0`. Either reuse `P0`, which muddies P0's meaning and metrics, or add a new code such as `S0 · Seed`. Stage codes are locked once events use them and U0.9's acceptance test lists them, so decide **before U0.9 G0**. |

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
