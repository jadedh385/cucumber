# ADR-0001 · Stack selection

**Unit:** [U0.1](../phase-0-foundations.md#u01--decision-register--stack-selection)
**Status:** Accepted · UI kit chosen by the G1 spike (see [Open items](#open-items))
**Date:** 2026-10-09, hosting and file storage 2026-10-11 · **Decided by:** Jade (Owner)
**Resolves:** [D-01](../decisions.md#conflicts-between-sop-and-deck),
[D-10](../decisions.md#conflicts-between-sop-and-deck),
[D-17](../decisions.md#added-2026-10-09)

## Decision

| Layer | Choice |
|---|---|
| App | Standalone **Cucumber**, not built inside Anemone |
| Language | **Python** |
| Framework | **Django 5.2 LTS** (security fixes until April 2028) |
| Front end | Django templates + **HTMX**, with **Alpine.js** for small interactions |
| UI styling | **Tailwind CSS** + a component kit (daisyUI first choice), checked in the spike |
| Rich widgets | Small TypeScript "islands" only where a screen needs them (QR scanner U4.6, lineage tree U2.3, charts U5.1, map U5.5) |
| Database | **PostgreSQL** |
| API | None for now. Added later on top of the services layer if a new front end is planned (see [Future front ends](#future-front-ends)) |
| Deploy | Docker Compose, same setup on any host |
| Network access | Internet-reachable through **Cloudflare Tunnel + Access** (D-10); no open inbound ports |
| Connectivity | **Online only** (D-17): Nursery 24/7 Wi-Fi, staff phone hotspots as backup; no offline mode |
| Hosting | **Cloud VPS in Singapore** (about US$5–15/month); provider picked at G1. Can move to a lab machine later (see [Hosting](#hosting)) |
| File storage | **Local disk on the VPS behind django-storages**; move to Cloudflare R2 by a settings change when photo volume grows |
| Label printing | **No app-to-printer link for now** (D-18): Cucumber lists what to print; staff print from the phone app |

## Context

- Jade is the Owner and wants to be able to read the code. Python reads more
  easily for them than TypeScript.
- Cucumber is an **internal, login-only** app for staff. It is mostly forms,
  lists and detail pages, used on phones (U0.10: 375 px, one-handed).
- Phase 0 needs login, sessions, roles, audit, migrations, Owner-editable
  reference lists and translation (D-16). Django ships all of these built in.
- The database must enforce rules itself: append-only events (U0.7), safe ID
  sequences (U0.8), non-negative counts and foreign keys (U0.2).
- Anemone (receipts → Zoho Books) handles money. Cucumber stores no money
  (SOP §2 principle 2). The two apps do different jobs.

## Options considered

### App: inside Anemone vs standalone

Standalone chosen. Building inside Anemone would mix plant tracking with
accounting code and put a working finance app at risk. The apps can still be
linked by IDs (D-13 option a), whichever language each uses.

### Framework and front end

| Criterion | Django + HTMX | Django + Inertia + React | Django API + React (Vite) | Django API + Next.js | Next.js only |
|---|---|---|---|---|---|
| Codebases / servers | 1 / 1 | 1 / 1 | 2 / 1 | 2 / 2 | 1 / 1 |
| Languages | Python | Python + TS | Python + TS | Python + TS | TS only |
| API to maintain | No | No | Yes | Yes | Partly |
| Login, roles, sessions | Built in | Built in | Built in, cross-app setup | Built in, shared across 2 servers | Assembled from libraries |
| Admin pages | ✅ | ✅ | ✅ | ✅ | ❌ |
| Translation (D-16) | 1 place | 2 places | 2 places | 2 places | 1 place |
| Offline (D-17) | Hard | Partial | Best | Possible | Possible |
| Rich screens | TS islands | ✅ | ✅ | ✅ | ✅ |
| Upgrade churn | Low | Medium | Medium | High | High |
| Readable for Owner | Best | Mixed | Mixed | Hardest | TS everywhere |
| Phase 0 effort | Lowest | Low–medium | Medium | Highest | Medium–high |

**Why not Next.js:** its main strengths (fast public pages, search ranking)
don't apply to an internal app behind a login. It adds the server / client
component split, which is easy to get wrong, fast-changing major versions,
and a self-hosted server that needs prompt security patching. Next.js stays a
good candidate for a **custom public storefront** later (see below).

**Why not GraphQL now:** see [Future front ends](#future-front-ends).

### Network access (D-10)

Staff need to enter data and work away from the lab (e.g. registering a new
cultivar off-site), so the app must be reachable over the internet.

| | Fully public | **Cloudflare Tunnel + Access** (chosen) | VPN (Tailscale) |
|---|---|---|---|
| How | Login page open to the internet | Cloudflare checks identity (email code) before anyone reaches Cucumber | Only devices on the private network |
| Staff experience | URL + login | URL + email code (remembered for days) + login | Install VPN app on every phone |
| Open ports on server | 80 / 443 | None | None |
| Extra cost | US$0 | US$0 (free up to 50 users; check current limits) | US$0 at small scale |
| Setup | ~2 days (firewall, Caddy, hardening) | ~2 days (`cloudflared` service, Access policy, hardening) | ~2 days + per-device setup |
| Before R1 also needs | U6.1 2FA + U6.6 rate limiting (~2 weeks) | Nothing extra; U6.1, U6.6 stay in Phase 6 | Nothing extra |

Chosen because it gives remote access with no extra cost and about two weeks
less work before go-live, and strangers never reach the login page. It also
makes a lab mini PC a workable host (no router port forwarding).

**Rule:** if the access gate is ever removed, U6.1 and U6.6 must be released
before the app stays public.

### Database

PostgreSQL over SQLite: PostgreSQL has database users and permissions
(needed to make events append-only), handles many people saving at once, and
supports check constraints and sequences.

## Concerns raised and answers

| Concern | Answer |
|---|---|
| "Will it look as nice as Next.js?" | How an app looks comes from styling and components, not the framework. Polished Next.js apps mostly use Tailwind + shadcn/ui. Django can use Tailwind (standalone tool, no Node) with daisyUI, Basecoat (shadcn look for plain HTML; check maturity) or django-cotton components. Proven in the spike on the lab phone. |
| Client-facing storefront | Likely Shopify, which brings its own look. Cucumber supplies data only (SKUs, calculated availability) via the Shopify API or an export. If a custom storefront is ever built, Django can add an API and that storefront could be Next.js. |
| "Can the front end be replaced later?" | Yes. The screens are rewritten; the system is not. See the rule below. |

## Architecture rule: thin views, rules in services

To keep the front end replaceable:

```
Screen (HTMX template)  →  View (thin: read input, call a service, show result)
                                  ↓
                     Service (the rules: "log subculture event", "promote plant")
                                  ↓
                     Models + database constraints
```

- Business rules and calculations live in **services**, never in views or templates.
- **Permissions are enforced in services** (on the server). Templates may hide
  buttons, but hiding is never the protection.
- Templates decide only what is *shown*, never what is *allowed*.

Added to the [G1 Design checklist](../gates.md#g1--design).

### What survives a front-end change

| Kept | Rewritten | Adjusted |
|---|---|---|
| Database, migrations, services, permissions, audit, admin, backups, deploy, unit and integration tests | Templates, HTMX snippets, page views | E2E tests (same flows, new selectors), translation strings (moved to the new front end) |

The change can be gradual: add an API, rebuild one screen at a time, and keep
HTMX where it works.

## Future front ends

A new front end would talk to an API built on the **same services**:

```
React / other front end  →  GraphQL (Strawberry)  ┐
                                                  ├→  Services  →  Models + DB
Shopify / integrations   →  REST (Django Ninja)   ┘
```

| | REST · Django Ninja | GraphQL · Strawberry |
|---|---|---|
| Default choice | ✅ | When needed |
| Strong at | Forms, lists, file uploads, simple integrations, per-endpoint permission tests | Nested data (plant → batches → events, lineage trees), several front ends needing different data |
| Costs | More endpoints as needs grow | Per-field permissions, N+1 queries (needs DataLoaders), query depth limits, harder caching, awkward file uploads |

Both generate TypeScript types for a front end. They can run side by side.
Graphene-Django is not recommended (older, less maintained).

## Consequences

- ✅ One codebase, one language for the Owner to read, lowest Phase 0 effort.
- ✅ Login, sessions, permissions, migrations, admin and translation come from Django.
- ✅ The front end can be replaced later without touching the rules.
- ✅ No offline mode needed (D-17: Nursery has 24/7 Wi-Fi, phone hotspots as
  backup), which removes the main weakness of HTMX for this app.
- ⚠️ Online only means a dropped connection must never lose an entry silently:
  a failed save shows a clear "not saved, retry" message and keeps what was typed
  (covered by U0.10 error states).
- ⚠️ Rich widgets need small TypeScript islands, a second toolchain for those pieces.
- ⚠️ Remote access depends on Cloudflare. Fallback if Cloudflare is down or
  dropped: open ports 443 behind Caddy (a few hours), then U6.1 and U6.6 become urgent.
- ⚠️ Cloudflare decrypts traffic in transit. Acceptable for plant data and staff
  accounts; Access policy lists each user's email; uploads are capped at 100 MB
  per request on the free plan.
- ⚠️ Django must trust Cloudflare's forwarded headers (HTTPS detection, CSRF
  trusted origins). Set up in U0.4.
- ⚠️ The Django admin bypasses services, so append-only and other critical
  rules must also be enforced in the database.

## Hosting

Decided 2026-10-11.

| | **A) Cloud VPS, Singapore** (chosen) | B) Lab mini PC via Cloudflare Tunnel | C) Hosted platform |
|---|---|---|---|
| Owner effort | Lowest: no hardware, provider handles power and network | UPS, disk health, physical access | Low, but less control |
| Lab power or internet outage | Remote users unaffected | Everyone cut off | Unaffected |
| Label printing | Not affected (no printer link, D-18) | Not affected | Not affected |
| Cost | About US$5–15/month | Hardware once + electricity | Usually higher at this size |
| Fit with Docker Compose | ✅ | ✅ | Weaker |

Chosen because the Owner wants to spend as little time as possible on
maintenance. Lab outages stop mattering for remote staff. D-18 no longer
affects this choice, because the app won't drive the printer.

**Moving to a lab machine later**, if that would cut costs: the same Docker
Compose file runs there. Restore the latest backup (U0.11), point the
Cloudflare Tunnel at the new machine, and switch off the VPS. Staff URLs stay
the same and no router ports need opening. Before moving, the lab machine needs
a UPS and off-site backups.

**Provider** is picked at G1 by these checks: Singapore region, automatic
snapshots, Docker support, monthly price, and a plain-language control panel.

**Size:** 2 GB RAM. Django, PostgreSQL and `cloudflared` together are tight on
1 GB; a handful of staff won't need more than 2 GB for a long time. Every
provider below can resize later.

Prices as listed in October 2026 (USD/month, 2 GB plan; check at sign-up):

| | Server | Automatic backups | Total | Notes |
|---|---|---|---|---|
| **DigitalOcean** (recommended) | $12 (1 vCPU, 50 GB) | Weekly +20% ($2.40) or daily +30% ($3.60); daily offered in Singapore | ~$14–16 | Simplest panel; largest library of Django + Docker guides |
| Vultr | $10 (1 vCPU, 55 GB) | +20% ($2), daily to monthly | ~$12 | Cheapest; panel almost as simple |
| Akamai (Linode) | $12 (1 vCPU, 50 GB) | $2.50, daily + weekly kept | ~$14.50 | Solid; fewer beginner guides now |
| AWS Lightsail | ~$12 (2 vCPU, 60 GB) | Free to switch on; $0.05/GB stored | ~$13 | Most for the money, but sits inside the AWS console and billing, harder for a newcomer |

Recommended: **DigitalOcean with daily backups**, for the plain panel and the
guides the Owner can follow alone. Vultr is the fine cheaper choice.
The provider's backups copy the whole server. They do **not** replace the
off-server database backups in U0.11.

## File storage

Decided 2026-10-11. Photo volume is unknown, so files start on the VPS disk
behind **django-storages**. Moving to Cloudflare R2 later needs a settings
change plus a one-off copy of existing files, with no code changes. Uploaded
files go into the backup with the database (U0.11). Revisit when photos pass
about 10 GB or the disk is 70% full.

## Personal data

Personal data is limited to staff accounts (name, email, role), so Thai PDPA
impact is small. No customer data (D-04).

## Open items

| Item | Options | Decided by |
|---|---|---|
| UI kit | daisyUI, Basecoat, or another Tailwind kit | G1 spike on the lab phone |
| VPS provider | Any that passes the checks under [Hosting](#hosting) | G1 |

## Spikes (U0.1 / G1)

The language spike was skipped: Django was chosen on readability and built-in
features. Hosting was decided on maintenance effort, so the two spikes now
compare **UI kits**:

1. The same tiny Django app styled with **daisyUI** and with **Basecoat**.
2. Each version includes: log in, record one event that can't be edited
   afterwards (blocked at the database), and one data-entry screen, checked
   one-handed on the actual lab phone.

The winner is deployed on the VPS behind Cloudflare Tunnel + Access for **G5**.

## Rejected or deferred

| Option | Status | Revisit when |
|---|---|---|
| Build inside Anemone | Rejected | D-13 at R1 |
| Lab mini PC hosting | Deferred | VPS cost is worth cutting; see [Hosting](#hosting) |
| Direct printing from the app | Deferred | U4.8 shows retyping or CSV import is too slow (D-18) |
| TypeScript back end / Next.js only | Rejected | — |
| Django API + React or Next.js front end | Deferred | A richer or offline-first front end is needed |
| GraphQL | Deferred | Several front ends, or deeply nested screens multiply REST endpoints |
| Custom storefront in Next.js | Deferred | Shopify no longer fits |
