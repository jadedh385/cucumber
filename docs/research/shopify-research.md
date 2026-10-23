# Shopify integration — research

**Date:** 2026-10-22 · **Status:** research only, nothing built · **For:** Owner, to scope the next phase

**Question:** how Cucumber can work with Shopify while **Cucumber stays the
source of truth for stock**, what it would cost, and what we would have to
build.

**Short answer:**

- Push stock **one way, Cucumber → Shopify**, and pull orders **Shopify → Cucumber**.
- Let Shopify handle the storefront, checkout, customers, discounts and shipping.
- Shopify Payments is **not available in Thailand**, so payments go through a
  Thai third-party provider inside Shopify checkout. Shopify adds its own fee
  of 2 % (Basic) or 1 % (Grow) on top of that provider's fee. Taking payment
  on our side instead is not practical (section 3).
- **Grow** becomes cheaper than Basic once card sales pass about
  **US$3,000 a month** (section 4).
- Two open decisions must be settled first, because the sync cannot be correct
  without them: **D-20 reservations** and **D-23 selling units**.

Section order: the plan cost depends on how customers pay (the Shopify fee
only applies to third-party providers), so **plans and costs come right after
payments**, as section 4. The five requested sections follow in their original
order around it.

---

## 0. What we know, what we assumed, what is still open

### Answered from the repository

| Question | Answer | Source |
|---|---|---|
| Current inventory system | **Cucumber**: Django 5.2 LTS + PostgreSQL, self-hosted (production MacBook), reached only through Cloudflare Tunnel + Access. Stock is an **append-only event log**; each batch's `live_count` is calculated from events; nothing is typed in directly. Plants have SKUs; batches sit in a location (**Lab**, **Nursery**) and a stage (P0 → P1 → P2 → A1 → P4). Every write is audited (U0.7). | ADR 0001, U0.2 design, U0.7 design |
| Where stock lives | `events` table → batch projections. "Available to sell" is **planned, not built** (U5.2: Portfolio plant, stage ≥ P4, open, not quarantined, units ≥ `min_saleable_qty`). | phase-5-analytics.md U5.2 |
| Customers / sales orders | **Zoho Books owns customers and vendors; Cucumber holds no customer data** (D-04). Pre-orders were to link to a Zoho sales order (D-20). | decisions.md |
| Storefront | ADR 0001: storefront "likely Shopify… Cucumber supplies data only (SKUs, calculated availability)". Custom storefront deferred. | ADR 0001 |
| Scale today | ~300 plants, ~1,000 open batches, ~100 entries a day, ~10 staff. 2 locations. | U0.2b G5 note, U0.5 notes |
| Region | Thailand (Thai PDPA in ADR 0001). | ADR 0001 |

### Questions for the Owner

Status after the Owner answers below. The full list of open questions, with
owners and next steps, is in [shopify-roadmap-plan.md](shopify-roadmap-plan.md#5-open-questions).

| # | Question | Why it matters | Status |
|---|---|---|---|
| Q1 | Which Shopify plan, and is it a new store or an existing one? | Sets the fee rate, staff seats, API speed. A store created after 2025-05-12 also pays the third-party fee on gift-card and store-credit amounts. | Partly: lowest-cost plan that fits. New or existing store still open. |
| Q2 | Expected online orders a month and average order value (THB)? | Decides Basic vs Grow (section 4) and whether polling is enough (section 1). | Partly: orders a month answered. Average order value still open. |
| Q3 | How many **sellable** SKUs, and in what units (single plant, bag of 5, jar)? | This is D-23; each selling unit becomes a Shopify variant. | Open |
| Q4 | Shopify storefront only, or other channels too (Lazada, Shopee, LINE, wholesale)? | Section 5. | Answered: store, live selling on social media, direct and partner sales. |
| Q5 | Which company sells: a Thai entity only, or is there one in a Shopify Payments country (e.g. Singapore)? Is it VAT-registered? | Payments (section 3) and tax settings. | Partly: Shopify Payments ruled out for a Thai entity. Entity elsewhere and VAT still open. |
| Q6 | Do you sell abroad (other currencies, export permits for plants)? | Currency fees; shipping rules. | Partly: yes, USA, EU / UK, Asia. Currencies and export permits still open. |
| Q7 | Which **Zoho Books edition** (Thai or global)? Do online orders need to land in Zoho as sales orders or invoices? | Zoho's own Shopify extension supports only the US edition (section 2). | Open |

### Owner answers (2026-10-22, for the plan comparison)

| Question | Answer |
|---|---|
| Tiers to compare | Basic, Grow, Advanced in full; **Plus as reference only** (what it unlocks, why it doesn't fit yet). |
| Order volume (Q2, partly) | **Per month**: up to 100 orders a month at first, growing to **250–300 a month within about 24 months**. Sales today: zero. |
| Shopify Payments for a Thai entity | **Not available** (Thailand not among the 41 countries; see section 3). A third-party provider or manual methods are needed. |
| Payment methods considered | PayPal, direct bank transfer, Wise, Revolut (Shopify Payments ruled out above). |
| Priority export markets (Q6) | **USA, EU / UK, Asia** (e.g. SG, HK, JP, MY). |
| Channels (Q4) | Shopify online store; live selling on social media; direct and partnership sales. |
| Plan default | Lowest-cost plan that covers current needs; a higher tier only when a specific need requires it. |
| Integrations | Custom-built is acceptable instead of Shopify apps. Plan limits on API access, custom checkout and webhooks must be flagged. |

### Assumptions in this report

- **A1** Shopify's own storefront and checkout are the main online channel.
- **A2** Online sales are modest at first (well under US$60,000 a month), so
  Basic or Grow fit and Advanced and Plus are not needed.
- **A3** Plants are shipped from one place (the Nursery). The Lab holds
  stock that is not ready to sell.
- **A4** D-04 stays: customers live in Shopify (and Zoho), not in Cucumber.
- **A5** All prices are in **USD**, as shown on shopify.com/th/pricing on
  2026-10-22. Shopify bills in USD, so the card or bank may add a foreign
  exchange fee (as already noted in ADR 0001).

---

## 1. Integration approaches and sync directions

### 1.1 Which way each piece of data flows

| Data | Direction | Owner of the truth | How |
|---|---|---|---|
| SKU identity (the link) | Cucumber → Shopify | Cucumber | Cucumber SKU written into the Shopify variant's `sku` field. A mapping table in Cucumber stores the Shopify variant and inventory-item IDs. |
| Product content (title, photos, description, SEO) | Edited in Shopify | **Shopify** | Marketing text belongs to the shop. Cucumber does not mirror it. |
| Price | **Decision needed** | Zoho, Cucumber or Shopify | Today nothing in Cucumber holds prices. Simplest: set prices in Shopify. If Zoho must stay the price list, someone has to keep the two in step. |
| **Stock level** | **Cucumber → Shopify only** | **Cucumber** | Push the sellable quantity into Shopify's `available` with `inventorySetQuantities`. |
| Orders (new, cancelled, edited, refunded) | Shopify → Cucumber | Shopify | Polling, and later webhooks (1.3). Cucumber turns each order line into a **reservation**. |
| Fulfilment (shipped, tracking number) | Cucumber → Shopify | Cucumber | When staff pack the order and pick the batches, Cucumber records the sale events and creates the Shopify fulfilment. |
| Customers | Stay in Shopify | Shopify / Zoho | Cucumber keeps only the order number and its lines (D-04, PDPA). |

### 1.2 How Shopify counts stock, and the trap

Shopify keeps several **quantity states** per item per location: `available`,
`committed` (sold, not yet shipped), `reserved`, `damaged`, `safety_stock`,
`quality_control`, `incoming`. `on_hand` is the sum of the first six.
[Manage inventory quantities and states]

- Apps can **set** `available` or `on_hand` (`inventorySetQuantities`), and
  **adjust or move** most other states.
- Apps **cannot** change `committed`. Shopify moves units from `available` to
  `committed` itself when an order comes in. [same page]

**The trap.** Suppose Cucumber pushes "available = 10" without knowing about an
order Shopify took a minute ago. That push hands back the unit the customer
just bought, and the next customer can buy a plant that isn't there.

**The fix (two parts, both must-have):**

1. **Reservations in Cucumber (D-20).** Each imported order line reserves
   units, and Cucumber pushes `sellable − reserved`. This decision is already
   open in the roadmap. Shopify makes it a precondition.
2. **Compare-and-swap on every push.** Shopify's `changeFromQuantity` field
   means "only apply if Shopify still shows X". If an order arrived in
   between, the push fails with `CHANGE_FROM_QUANTITY_STALE`. Cucumber then
   imports orders first and retries. Shopify documents opting out (`null`)
   when your app is the source of truth, but **we should not opt out**: the
   check is what closes the gap above. Every push should also carry an
   idempotency key and a `referenceDocumentUri` pointing at the Cucumber
   operation, so the change shows up in Shopify's history with our ID on it.
   [Manage inventory quantities and states]

### 1.3 Polling or webhooks

Cucumber sits behind Cloudflare Access with **no public endpoint** (ADR 0001).
Shopify webhooks need a public HTTPS address Shopify can call.

| | **Polling** (recommended first) | **Webhooks** (add later) |
|---|---|---|
| How | A Cucumber job asks Shopify every few minutes for orders changed since the last run (`updated_at`). | Shopify calls Cucumber on `orders/create`, `orders/cancelled`, `orders/edited`, `refunds/create`. |
| Network | Outbound only. Fits today's design. | Needs a narrow Access bypass (like `/health/`), HMAC check on every call (`X-Shopify-Hmac-Sha256`), and rate limiting. |
| Delay | A few minutes | Seconds |
| Reliability | Simple | Shopify says order is **not guaranteed**, duplicates happen, it retries **up to 8 times over 4 hours**, wants an answer within **5 seconds**, and removes the subscription if failures persist. It recommends a **reconciliation job anyway**. [Webhooks overview; Troubleshooting webhooks] |

Shopify itself recommends the polling job even when you use webhooks, so
polling must be built either way and webhooks only shorten the delay. With
compare-and-swap (1.2), a few minutes of delay cannot oversell. It only means
a reservation appears a few minutes after the sale. If the production Mac is
down, Shopify keeps selling against its last numbers, and Cucumber catches up
on restart.

Not verified here: Shopify can also deliver webhooks to Google Pub/Sub or
Amazon EventBridge, which would avoid opening a public path. Check this
before choosing webhooks.

### 1.4 Ways to plug Cucumber in

| Option | What it is | Fit |
|---|---|---|
| **A. Custom app + normal Shopify location** (recommended) | A private app with Admin API access. "Nursery" is a Shopify location whose `available` Cucumber sets. Cucumber marks orders shipped. | Least work; all features above. |
| B. Fulfilment-service app | Cucumber registers as a fulfilment service, gets its own Shopify location, accepts fulfilment requests, and can answer stock queries at `/fetch_stock.json`. [Fulfillment service apps; Build for fulfillment services] | Built for third-party warehouses. Needs a public callback URL and more moving parts, with no gain at our size. |
| C. Export / CSV | Upload stock by hand | Fallback only; error-prone. |

**Technical notes for option A**

- Use the **GraphQL Admin API**. REST has been "legacy" since 2024-10-01, and
  new public apps must use GraphQL from 2025-04-01. [Shopify changelog]
- Since **2026-01-01**, new custom apps cannot be created in the store admin.
  They are made in the **Dev Dashboard**. Third-party sources say the new
  tokens use client credentials and **expire after 24 hours**, so Cucumber
  must refresh them. *Not verified against Shopify's own docs; check at
  design.*
- Rate limit: **100 points a second** on standard plans, 200 on Advanced,
  1,000 on Plus. [GraphQL rate limits] At our size this is far more than
  enough. Bulk operations (for a full resync) have no rate limit.
- Up to **2,048 variants per product** (since 2025-10-15). [Shopify changelog]
  A product is still said to allow at most 3 options. *That limit comes from
  community sources only.*
- Order creation by API (`orderCreate`) exists for importing orders from
  other systems. On trial and development stores it is limited to **5 orders
  a minute**. [orderCreate]

---

## 2. Shopify capabilities: rely on Shopify or build ourselves

| Area | Label | Reason |
|---|---|---|
| **Inventory: counts** | **Build ourselves** (already ours) | Cucumber is the source of truth. Shopify only shows a number we push. |
| **Inventory: sellable quantity** | **Build ourselves** (must-have) | U5.2 + D-23. Shopify cannot know about stage, quarantine or pack size. |
| **Inventory: reservations** | **Build ourselves** (must-have) | D-20. Without it, pushes can oversell (1.2). |
| Inventory: oversell guard at checkout | **Rely on Shopify** | Shopify refuses checkout when `available` hits 0, provided the variant is set to stop selling when out of stock. *Not separately verified here.* |
| **Orders: taking and storing them** | **Rely on Shopify** | Checkout, order records, cancellations, refunds, order emails. |
| Orders: copy in Cucumber | **Build ourselves** (thin) | Only the order ID, number, lines and status, to drive reservations and picking. No addresses (PDPA, D-04). |
| Orders: into Zoho Books | **Decision needed** | Zoho's own *Shopify Extension Lite* supports **only the US edition** of Zoho Books. Third-party apps from about US$6 a month exist. Options: an app, our own sync, or monthly summaries entered by hand. Depends on Q7. |
| **Fulfilment: which batch the plants come from** | **Build ourselves** (must-have) | Only Cucumber knows batches. The pick step writes the sale events. |
| Fulfilment: shipped status, tracking, customer email | **Rely on Shopify** | Cucumber calls `fulfillmentCreate` and Shopify notifies the customer. |
| Fulfilment: shipping labels and rates | **Decision needed** | Whether Shopify Shipping works in Thailand was **not verified**. Otherwise use a courier app or book shipments by hand. |
| **Product catalogue: SKU and variants** | **Build ourselves** (mapping only) | Mapping table plus a check that every sellable Cucumber SKU has exactly one Shopify variant. |
| Product catalogue: content and photos | **Rely on Shopify** | Marketing content. Creating draft products from Cucumber is nice-to-have. |
| Product catalogue: price | **Decision needed** | See 1.1. |
| **Customers** | **Rely on Shopify** (and Zoho) | D-04: no customer data in Cucumber. Keeps PDPA scope small. |
| **Discounts** | **Rely on Shopify** | Built-in discount codes and automatic discounts. Custom discount logic (Shopify Functions) in a **custom app needs Plus**. [Shopify Functions] Not needed. |
| B2B / wholesale price lists | **Rely on Shopify if needed** | Available on Basic, Grow, Advanced and Plus. Features vary by plan. [Shopify B2B] |
| Payments | See section 3 | — |

---

## 3. Payments

### Facts

- **Shopify Payments is not offered in Thailand.** It covers 41 countries,
  including Singapore, Hong Kong, Japan, Australia and New Zealand. If your
  country isn't listed you "need to use a third-party payment provider."
  [Shopify Payments supported countries]
- **Third-party providers** work in two ways. *Direct* providers take payment
  on the Shopify checkout page. *External* providers send the buyer to a
  payment page hosted elsewhere. They are switched on from the Payments page
  in the Shopify admin. [Third-party payment providers]
- **Shopify adds a third-party transaction fee** on every order paid through
  them: **2 % Basic, 1 % Grow, 0.6 % Advanced, 0.2 % Plus**. This is on top of
  the provider's own fee. [Pricing page; Fees and costs]
- **Manual payment methods** (bank transfer, cash on delivery, cash) carry
  **no Shopify transaction fee**. [Fees and costs] A PromptPay QR shown as a
  "bank transfer" method would fall under this. The catch: staff must check
  each payment by hand before shipping.
- **Building our own gateway is closed to us.** Only approved Shopify
  Partners can build payment apps, and a merchant's own custom payment
  extension is **limited to eligible Plus merchants**. [Payments apps]

### Thai providers that work with Shopify (to confirm in the admin)

Third-party guides name **Opn Payments (ex-Omise)**, **2C2P**, **Xendit**
(which took over GB Prime Pay), **Pay Solutions**, **PayPal** and **HitPay**.
One guide quotes Opn at about **3.65 % for cards** and **1.65 % for
PromptPay**. *None of this comes from Shopify's own documentation.* Check the
store's Payments page for the real list, and ask the providers for written
rates.

### Taking payment on our side instead

| Way | What it means | Verdict |
|---|---|---|
| Own gateway inside Shopify checkout | Needs Partner approval, or Plus (from US$2,300 a month) | Not practical |
| Own checkout outside Shopify | Use Shopify only as a catalogue. Take payment on our own page, then record the order through the API as paid. | Possible, but we would build and secure a checkout. Card data rules (PCI) then apply to us, and we lose Shopify's checkout. Not worth it at our size. |
| Manual methods in Shopify checkout | PromptPay QR or bank transfer, checked by staff | Practical. No Shopify fee, but manual checking and slower shipping |

### Recommendation

**Use Shopify checkout with one Thai third-party provider for cards and
PromptPay.** Add a manual bank-transfer / PromptPay option if many customers
prefer it, since that avoids Shopify's fee. Do not try to process payments on
our side.

**Open questions that could change this:**

- Q5: does the business have an entity in a Shopify Payments country? If yes,
  Shopify Payments would remove the extra fee, but cross-border and currency
  fees (2 %) then apply.
- Which providers actually appear in the store's Payments page.
- The providers' written rates.

---

## 4. Shopify plans and projected costs

### Plans (shopify.com/th/pricing, 2026-10-22, USD)

| Plan | Monthly billing | Yearly billing (per month) | 3rd-party fee | Staff accounts | Locations |
|---|---|---|---|---|---|
| Basic | $25 | $19 | 2 % | not included | 10 |
| **Grow** | $65 | $49 | 1 % | 5 | 10 |
| Advanced | $399 | $299 | 0.6 % | 15 | 10 |
| Plus | from $2,300 (3-year term) | — | 0.2 % | unlimited | 200 |

No setup fee. Trial: 3 days free, then $1 a month for 3 months on most plans.
[Pricing page] *Plus:* about $2,500 on a 1-year term, plus a variable fee on
large sales that Shopify does not publish (third-party sources).

### Cost per month (yearly billing, cards through a third-party provider)

Formula: **plan + Shopify fee % × card sales**. The provider's own fee
(e.g. ~3.65 %) is the same on every plan, so it is left out of this
comparison. Add it for the full cost.

| Card sales / month | Basic | Grow | Advanced |
|---|---|---|---|
| $1,000 | **$39** | $59 | $305 |
| $3,000 | $79 | **$79** | $317 |
| $5,000 | $119 | **$99** | $329 |
| $20,000 | $419 | **$249** | $419 |
| $100,000 | $2,019 | $1,049 | **$899** |

**Break-even points**

- **Basic → Grow:** about **$3,000 a month** of card sales on yearly billing
  ($30 ÷ 1 %), or $4,000 on monthly billing.
- **Grow → Advanced:** about **$62,500 a month** ($250 ÷ 0.4 %).
- Sales paid by **manual PromptPay or bank transfer** don't count, because
  they carry no Shopify fee.

Basic includes **no staff accounts**. If two or more people need the Shopify
admin (packing, customer service), Grow (5 accounts) may be needed regardless
of sales. *Check what "not included" means in practice.*

### Fees that are easy to miss

| Fee | Size | Source |
|---|---|---|
| Shopify third-party fee **on top of** the provider fee | 2 % / 1 % / 0.6 % | Pricing page |
| Same fee on **gift-card and store-credit** amounts (stores created after 2025-05-12) | plan rate | Fees and costs |
| Payment provider fee | ~3.65 % card, ~1.65 % PromptPay (Opn, third-party guide) | unverified |
| Foreign exchange fee from your bank or card (Shopify bills in USD) | bank's rate | ADR 0001 |
| Apps (Zoho sync, courier, reviews…) | ~$6+ a month each | App Store listings |
| Selling on marketplaces through Shopify | free for the first 50 orders a month, then 1 % up to $99 a month | Pricing page |
| POS Pro (if selling in person at the nursery with Shopify POS) | $89 a month per location | Pricing page |
| Paid theme, domain | one-off / yearly | *not researched* |
| Thai VAT on Shopify's fees | unknown | *not verified*: ask an accountant |
| Our own running cost | Developer time for the sync. Production Mac uptime matters more once orders depend on it. | — |

**Mid- to long-term view:** start on **Basic, or Grow if more than one person
needs the admin**, with yearly billing once sales are steady. Move to Grow
when card sales pass ~$3,000 a month. Advanced is only worth it near
$60,000 a month. Plus stays out of reach unless sales grow a lot.

---

## 5. More sales channels later

### Already platform-neutral

- The **event log, batches, stages, locations** and the audit trail (U0.2,
  U0.7).
- **Sellable quantity** (U5.2) and **reservations** (D-20), *if* they are
  designed with a `channel` field from the start.
- The **services layer** ("rules in services", ADR 0001), which any
  integration calls, and the planned REST API (Django Ninja).
- The **pick-a-batch → sale event** step, which is the same whatever sold the
  plant.

### Needs a change to support more channels

| Part | Change |
|---|---|
| SKU ↔ listing mapping | One table keyed by **(channel, external ID)**, not a Shopify-only column. |
| Order import | One adapter per channel. All of them produce the same "order line → reservation" record, made idempotent on (channel, external order ID). |
| Stock push | One pusher per channel, plus a rule for **sharing stock**: every channel sees all sellable units, or each channel gets a fixed share. With plants in small numbers, sharing everything risks selling the same plant twice on two channels. |
| Shopify-only pieces | Quantity states, `changeFromQuantity`, fulfilment orders, webhook HMAC. These stay inside the Shopify adapter. |

**Decision needed:** which system is the **hub** for other channels?

- **Cucumber as hub:** we build one adapter per marketplace.
- **Shopify as hub:** use Shopify's marketplace connector. Free for 50
  orders a month, then 1 % up to $99 a month. Cucumber keeps talking only to
  Shopify. Less code for us, but each marketplace's stock comes through
  Shopify.

Lazada, Shopee and LINE APIs were **not researched**.

---

## 6. Features to build on our side

### Must-have

| # | Feature | Why |
|---|---|---|
| M1 | **Sellable quantity per SKU** (U5.2, with D-23 selling units decided) | This is the number we push. Pack sizes decide what a Shopify variant is. |
| M2 | **Reservations** (D-20), with a channel field | Stops our pushes from handing back plants already sold (1.2). |
| M3 | **SKU ↔ Shopify mapping** (variant ID, inventory-item ID, location ID) plus a mismatch check | Everything else hangs on this link. A missing or duplicate mapping must show up, not fail silently. |
| M4 | **Stock push** with compare-and-swap, idempotency key and Cucumber reference | Safe, repeatable pushes that can be traced in Shopify's history. |
| M5 | **Order import by polling**: new, cancelled, edited, refunded; idempotent on Shopify order ID | Creates and releases reservations. Shopify says reconciliation is needed even with webhooks. |
| M6 | **Pack and ship step**: pick batches, write sale events, send the Shopify fulfilment with tracking | Turns a reservation into real stock movement and tells the customer. |
| M7 | **Sync health page** (Admin): last successful push and import, failed items, drift between Cucumber and Shopify | With the Mac self-hosted, someone must see quickly when the sync stops. |
| M8 | **App credentials and token refresh** (Dev Dashboard app, secret in `secrets.env` and Bitwarden) | New custom apps use expiring tokens (to verify). Without the refresh, the sync stops within a day. |
| M9 | **Audited integration writes** (`audited()`, System actor, `via=shopify`) | Keeps U0.7's rule that every write names who made it. |

### Nice-to-have

| # | Feature | Why |
|---|---|---|
| N1 | Webhooks through a narrow Access bypass with HMAC check | Seconds instead of minutes. Only worth it if order volume grows. |
| N2 | Create draft Shopify products from new Portfolio plants | Saves typing when the range grows. |
| N3 | Zoho Books order sync (if not done by an app) | Depends on Q7. |
| N4 | Discord alert when a SKU sells out or the sync fails | Fits the planned U2.8 alerts. |
| N5 | Stock split across channels | Only needed once a second channel exists (section 5). |
| N6 | Full resync with bulk operations | Faster recovery after long downtime. Polling can also catch up, just more slowly. |

---

## Sources

Shopify, checked 2026-10-22:

- [Shopify pricing (Thailand)](https://www.shopify.com/th/pricing) · [Shopify pricing](https://www.shopify.com/pricing)
- [Shopify Payments supported countries](https://help.shopify.com/en/manual/payments/shopify-payments/supported-countries)
- [Third-party payment providers](https://help.shopify.com/en/manual/payments/third-party-providers)
- [Fees and costs](https://help.shopify.com/en/manual/international/pricing/fees)
- [Payments apps](https://shopify.dev/docs/apps/build/payments)
- [Manage inventory quantities and states](https://shopify.dev/docs/apps/build/orders-fulfillment/inventory-management-apps/manage-quantities-states)
- [GraphQL Admin rate limits](https://shopify.dev/docs/apps/build/apis/graphql-admin/rate-limits) · [API limits](https://shopify.dev/docs/api/usage/limits)
- [Webhooks overview](https://shopify.dev/docs/apps/build/webhooks) · [Troubleshooting webhooks](https://shopify.dev/docs/apps/build/webhooks/troubleshooting-webhooks) · [Webhook topics](https://shopify.dev/docs/api/admin-graphql/latest/enums/WebhookSubscriptionTopic)
- [Fulfillment service apps](https://shopify.dev/docs/apps/build/orders-fulfillment/fulfillment-service-apps) · [Build for fulfillment services](https://shopify.dev/docs/apps/build/orders-fulfillment/fulfillment-service-apps/build-for-fulfillment-services)
- [orderCreate](https://shopify.dev/docs/api/admin-graphql/latest/mutations/orderCreate)
- [Shopify Functions](https://shopify.dev/docs/apps/build/functions) · [Shopify B2B](https://help.shopify.com/en/manual/b2b)
- [New public apps must use GraphQL (changelog)](https://shopify.dev/changelog/starting-april-2025-new-public-apps-submitted-to-shopify-app-store-must-use-graphql)
- [Variant limit is now 2,048 (changelog)](https://shopify.dev/changelog/the-product-variant-limit-is-now-2048-for-all-merchants)

Not from Shopify (treat as unverified):

- [No new legacy custom apps from 2026-01-01 (Shopify dev community)](https://community.shopify.dev/t/starting-january-1-2026-you-will-not-be-able-to-create-new-legacy-custom-apps-this-will-not-impact-any-existing-apps/26798)
- [Shopify payment gateways in Thailand (Xendit)](https://www.xendit.co/en-th/blog/top-payment-gateway-for-shopify-ecommerce-brands-in-thailand-2026/) · [Best payment gateways in Thailand (Statrys)](https://statrys.com/blog/best-payment-gateways-in-thailand)
- [Shopify Extension Lite for Zoho Books (Zoho Marketplace)](https://marketplace.zoho.com/app/books/shopify-extension-lite-for-zoho-books)
- Shopify Plus variable fee: agency guides, e.g. [elogic](https://elogic.co/blog/shopify-plus-pricing-2026/)

### Not verified

- Thai VAT on Shopify's fees.
- Whether Shopify Shipping works in Thailand.
- Webhook delivery to Pub/Sub or EventBridge.
- Token expiry for Dev Dashboard apps.
- The 3-option limit per product.
- The real list of Thai payment providers and their rates.
- The Shopify setting that stops selling at zero stock.
