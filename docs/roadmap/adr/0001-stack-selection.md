# ADR-0001 · Stack selection

**Unit:** [U0.1](../phase-0-foundations.md#u01--decision-register--stack-selection)
**Status:** Accepted · UI kit **daisyUI**, chosen by the Owner from the G1 spike (2026-10-11)
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
| UI styling | **Tailwind CSS + daisyUI 5**, chosen over Basecoat in the U0.1 spike (2026-10-11) |
| Rich widgets | Small TypeScript "islands" only where a screen needs them (QR scanner U4.6, lineage tree U2.3, charts U5.1, map U5.5) |
| Database | **PostgreSQL** |
| API | None for now. Added later on top of the services layer if a new front end is planned (see [Future front ends](#future-front-ends)) |
| Deploy | Docker Compose, same setup on any host |
| Network access | Internet-reachable through **Cloudflare Tunnel + Access** (D-10); no open inbound ports |
| Connectivity | **Online only** (D-17): Nursery 24/7 Wi-Fi, staff phone hotspots as backup; no offline mode |
| Hosting | **Self-hosted**: start on the Owner's spare MacBook Air M2; a Linux mini PC if self-hosting stays. **Cloud VPS in Singapore is the fallback** if self-hosting proves a hassle (see [Hosting](#hosting)) |
| File storage | **Local disk on the server behind django-storages**; move to Cloudflare R2 by a settings change when photo volume grows |
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

Decided 2026-10-11 by the Owner: **go live self-hosted (B); move to the cloud
(A) if it proves a hassle.** Earlier the same day A was chosen for least effort;
the Owner chose to try B first to keep running costs near zero.

| | A) Cloud VPS, Singapore (fallback) | **B) Self-hosted machine** (chosen) | C) Hosted platform |
|---|---|---|---|
| Owner effort | Lowest: provider handles power and network | Power, UPS, updates, occasional visit | Low, but less control |
| Power or internet cut where the server is | Not affected | **Everyone loses Cucumber** until it's back | Not affected |
| Cost | ~US$15.60/month | Electricity ~฿30–40/month + hardware once | Usually higher |
| Fit with Docker Compose | ✅ | ✅ | Weaker |

**The server doesn't have to be in the lab.** Cucumber doesn't drive the
printer (D-18) and staff reach it through Cloudflare Tunnel, so the machine
goes wherever the power and internet are most reliable. No router ports are
opened.

### Machine

| Machine | Status | Notes |
|---|---|---|
| **Spare MacBook Air M2** (8 GB, 512 GB) | **Start here**, free | Its battery rides through short power cuts. Catches: battery wear (set the 80% charge limit), no Ethernet socket (USB-C adapter), Docker runs inside a hidden Linux VM (2–4 GB of memory), and FileVault waits for a password after an unplanned restart |
| **Linux mini PC** | Upgrade if self-hosting stays | Best fit: restarts on its own after a power cut, no password wait, no battery. Minimum 4 cores (e.g. Intel N100), 8 GB RAM (16 GB comfortable), 256 GB SSD (512 GB comfortable), Ethernet, BIOS "power on after AC loss", Ubuntu Server 24.04 LTS. About ฿6,000–10,000 new; used business mini PCs (ThinkCentre Tiny, EliteDesk Mini, OptiPlex Micro) cost less |
| Mac mini M4 | Not chosen | Very efficient (3–4 W idle) and restarts after power cuts, but about ฿21,000–29,000 and keeps the macOS catches (Docker VM, FileVault password) |

### Set-up checklist (U0.4)

- **MacBook:** macOS 26.4 or later with the battery **charge limit at 80%**;
  never sleeps on power; macOS updates download but install only when the
  Owner chooses (no surprise restarts); Docker Desktop starts at login;
  USB-C Ethernet adapter.
- **UPS** for the internet router (and the Mac's charger). A server on battery
  is no use if the router is off.
- **FileVault** (open, decide at U0.4): keep it on and have someone at the
  location type the password after an unplanned restart, or turn it off and
  rely on encrypted backups. On means the data is safe if the laptop is stolen.
- **Remote management** through Cloudflare Access (SSH), so the Owner can
  look after it from anywhere without opening ports.
- **Off-site backup (U0.11) running before go-live**, encrypted, to cloud
  storage (e.g. Cloudflare R2, free up to 10 GB). This is what makes a dead or
  stolen machine survivable.
- **Uptime alert:** a free outside check emails the Owner when Cucumber can't
  be reached. It also measures the "hassle" below.

### When to move to the cloud

Move to A if **any** of these happen:

- Cucumber is unreachable for more than 4 hours at once during working hours,
  or more than twice in a month;
- someone has to go to the machine (type a password, restart it) more than
  once a month;
- looking after it takes the Owner more than about 1 hour a week;
- the machine fails.

**How to move:** create the cloud server, restore the latest off-site backup
there, point the Cloudflare Tunnel at it, and switch the old machine off. It
takes a few hours, and staff keep the same URL. The same steps move back to a
local machine later.

### Fallback: cloud VPS

Kept from the October 2026 research so the move is quick. **Provider** checks:
Singapore region, automatic snapshots, Docker support, monthly price, and a
plain-language control panel.

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

Also looked at (October 2026 research):

| Option | Why not chosen |
|---|---|
| Hetzner, Singapore | Cheap in Europe, but Singapore plans cost more and include only 0.5 TB traffic; stricter sign-up checks |
| Thai providers in Bangkok (e.g. NIPA Cloud, Nine Web, VPSThai) | Slightly faster from the lab and billed in baht, but fewer English and Docker guides, uneven quality, and usually higher prices (from about US$8–45/month). Singapore is only about 30 ms further away, which staff won't notice |
| Managed PostgreSQL (DigitalOcean, from about US$15/month extra) | The provider runs database updates and backups. Not needed for a few staff; PostgreSQL runs in Docker on the same server and U0.11 handles backups. Revisit if database upkeep becomes a burden |

**Things easy to overlook:**
- Bills are in US dollars on a card, so the bank may add a foreign-exchange fee.
- No lock-in: everything runs from one Docker Compose file, so moving provider
  means restoring a backup elsewhere (the same steps as moving to a lab machine).
- If the provider account is ever closed or locked, the server and its backups
  go with it. That is why U0.11 keeps a copy of the database **outside** the
  provider.
- Cloudflare Tunnel sends very little traffic, so bandwidth limits don't matter
  at this size.

**PDPA:** only staff accounts are personal data. Storing them on a server in
Singapore that only the business can access may not count as a cross-border
transfer under Thai guidance. If it does, a standard contract clause covers it
(for example the provider's data processing agreement). Low risk; confirm with
an adviser before R1 if in doubt.

## File storage

Decided 2026-10-11. Photo volume is unknown, so files start on the server's disk
behind **django-storages**. Moving to Cloudflare R2 later needs a settings
change plus a one-off copy of existing files, with no code changes. Uploaded
files go into the backup with the database (U0.11). Revisit when photos pass
about 10 GB or the disk is 70% full.

## Personal data

Personal data is limited to staff accounts (name, email, role), so Thai PDPA
impact is small. No customer data (D-04).

## UI kit

Decided 2026-10-11 by the Owner after trying the spike (`spike/` on branch
`spike/u0.1-ui-kit`) on an iPhone 13: **daisyUI 5** over Basecoat 1.0.

- The spike loads daisyUI from a CDN. The real app builds its CSS with the
  **Tailwind standalone CLI** and daisyUI's bundled plugin file, so there is no
  Node toolchain and no runtime CDN (U0.10).
- The look (theme colours, rounding) is tuned in U0.10. daisyUI themes make a
  later restyle a settings change, not a rewrite.
- Still to check on an **Android** staff phone: at G5, when the spike app runs
  on the self-hosted machine.

## Open items

| Item | Options | Decided by |
|---|---|---|
| FileVault on the MacBook | On (someone types the password after a restart) or off (encrypted backups only) | U0.4 |
| Fallback cloud provider | DigitalOcean recommended (see [Fallback](#fallback-cloud-vps)) | Only when a move is triggered |

## Spikes (U0.1 / G1)

The language spike was skipped: Django was chosen on readability and built-in
features. Hosting was decided on maintenance effort, so the two spikes now
compare **UI kits**:

1. The same tiny Django app styled with **daisyUI** and with **Basecoat**.
2. Each version includes: log in, record one event that can't be edited
   afterwards (blocked at the database), and one data-entry screen, checked
   one-handed on the actual lab phone.

The winner is deployed on the self-hosted machine behind Cloudflare Tunnel + Access for **G5**.

## Rejected or deferred

| Option | Status | Revisit when |
|---|---|---|
| Build inside Anemone | Rejected | D-13 at R1 |
| Cloud VPS hosting | Fallback | Self-hosting proves a hassle; see [When to move to the cloud](#when-to-move-to-the-cloud) |
| Mac mini as server | Rejected | — |
| Direct printing from the app | Deferred | U4.8 shows retyping or CSV import is too slow (D-18) |
| TypeScript back end / Next.js only | Rejected | — |
| Django API + React or Next.js front end | Deferred | A richer or offline-first front end is needed |
| GraphQL | Deferred | Several front ends, or deeply nested screens multiply REST endpoints |
| Custom storefront in Next.js | Deferred | Shopify no longer fits |
