# Runbook · Cloudflare Zero Trust: Access, tunnels, SSH, uptime

**For:** the Owner, with Claude checking from the Owner's Mac. **Why:** U0.4b
AC19–AC23 ([design §6–§9](../roadmap/units/u0.4b-design.md#7-access-the-email-check-ac19-ac20)).
This is step 2 of the design's order of work (§12): the account, the email
lists and the Access applications. Part B is step 4 (staging tunnels and
the first phone login); production's tunnels (step 6) come later.

**What it changes:** nothing anyone can see yet. No name points at a tunnel,
so the Access applications guard addresses that don't answer. Email, the
website and the DNS records are not touched.

**Time:** about 45 minutes, any day, in the browser only.

**Menu names.** Cloudflare renames Zero Trust menus often. If a menu below
isn't there, use the dashboard's search box with the last word (e.g.
*Lists*, *Login methods*).

## Part A · Account, lists and Access

### A1. Zero Trust account (Owner, 10 min)

`one.dash.cloudflare.com` (Cloudflare One) → **Zero Trust** → **Overview**.
The *Account details* box shows the team name and plan.

- **Plan:** **Zero Trust Free** (up to 50 people). Cloudflare may ask for a
  card; nothing is charged on Free.
- **Team name:** `southeastcanopy`. The login page becomes
  `southeastcanopy.cloudflareaccess.com`. Cloudflare may already have made
  the account with a random name (e.g. `muddy-sunset-…`): change it with
  *Account details* → **Settings**. Safe now, since nothing uses it yet.
- Save the team name in the Bitwarden entry for Cloudflare (notes).

### A2. Login method (Owner, 2 min)

Zero Trust → **Integrations → Identity providers** → *Add new identity
provider* → **One-time PIN**.

- New accounts since mid-2026 start with only **Cloudflare** (sign in with a
  Cloudflare account), not One-time PIN. Staff have no Cloudflare accounts,
  so it is left on the account but **unticked on every application** (A5).
- Add no other method (design §7: email code only).

### A3. No email lists (decided 2026-10-17)

Design §7 planned two Cloudflare *Lists*. Not needed: the addresses go
straight into the reusable `Staff` and `Admins` policies (A4), and each
policy is shared by all its applications, so a change is still made in one
place. Type each address in lower case, exactly as the mailbox spells it.

### A4. Policies (Owner, 5 min)

Access controls → **Policies** → *Add a policy*. Three reusable policies:

| Policy name | Action | Include | Session |
|---|---|---|---|
| `Staff` | Allow | *Emails* → every staff address, Owner included | Same as application |
| `Admins` | Allow | *Emails* → the Owner's work address **only** | Same as application |
| `Health check` | **Bypass** | *Everyone* | — |

In the form: name and action at the top; under **Add rules → Include**, the
selector (*Emails*, or *Everyone*) and then the value. Bypass may ask you
to confirm: it lets anyone through, which is the point for `/health/` only.
To change an action later: the policy → **Configure**.

### A5. Access applications (Owner, 15 min)

Access controls → **Applications** → *Add an application* → **Self-hosted**
(may read *Self-hosted and private*). One per row; under **Access
policies**, *Select existing policies*. Under *Public hostname*: subdomain, then `southeastcanopy.com`,
then the path (blank unless shown).

| Application name | Subdomain | Path | Policy | Session duration |
|---|---|---|---|---|
| `Cucumber` | `cucumber` | — | `Staff` | 1 month |
| `Cucumber health` | `cucumber` | `health/` | `Health check` | (default) |
| `Cucumber staging` | `cucumber-staging` | — | `Staff` | 1 month |
| `Cucumber SSH` | `cucumber-ssh` | — | `Admins` | 24 hours |
| `Cucumber Staging SSH` | `cucumber-staging-ssh` | — | `Admins` | 24 hours |

On each application:

- **Login methods** tab: *Accept all available identity providers* off; in
  *Choose available identity providers* tick only **One-time PIN** (not
  *Cloudflare*); turn on **Instant Auth** if offered (skips the "choose a
  method" page).
- A warning that the name has **no DNS record** is expected: the tunnels add
  the records later. Save anyway.
- Leave the *App Launcher* off, and **Allow clientless access** off. If it's
  on, saving fails with `use_clientless_isolation_app_launcher_url can only
  be enabled for apps with private destinations` (it's for private IPs, not
  public names).
- Leave **authenticate via WARP / Cloudflare One Client** off (staff use the
  email code, not the device client). If it's on, saving fails with
  `allow_authenticate_via_warp cannot be set until …`.

`Cucumber health` covers only `/health/` and anything under it (design §7).
Access uses the most specific match, so the rest of `cucumber.…` still asks
for the code.

### A6. Checks (Owner and Claude, 5 min)

| Check | Who | How |
|---|---|---|
| Policy test | Owner | **Skip until step 4.** Cloudflare's *Test policies* only works for an address that has logged in once (else `invalid_user_id`, "0 policies evaluated"). Nobody can log in before a tunnel exists |
| Setup | Owner | Screenshots of the Applications list, the Policies list and each policy's rule, for Claude to compare with A4–A5 |

The real AC19/AC20 test (a phone gets a code, a stranger doesn't) needs a
tunnel. It runs at step 4 (staging) and step 6 (production).

### A7. Uptime account (Owner with Claude, later)

Picked at sign-up after reading the free plan's terms (design §9, Q2). It
only watches production, so it can wait until step 6.

### Undo

Delete the applications and policies. Nothing points at them yet.

## Part B · Staging tunnels and the first phone login (step 4)

### B1. Tunnels

Made and started as in the [Asus runbook, Phase 7](asus-staging-setup.md#phase-7--cloudflare-tunnels-u04b-jade--claude-45-min):
`cucumber-staging` (app, in Docker) and `cucumber-staging-admin` (SSH,
systemd). Each route is a **Published application**, never *Private
hostname*. Delete any tunnel made by mistake (the dashboard names it
*Cloudflared* if the name box was left alone) with its saved token.

### B2. SSH from away (AC22)

Mac set-up in Phase 7 step 4. Test with the Mac **on the phone's hotspot**:
`ssh cucumber-staging-remote hostname` → `cucumber-staging`.

### B3. Phone test (AC19, AC20)

Phone with **Wi-Fi off** (mobile data):

| # | Do | Expect |
|---|---|---|
| 1 | Open `https://cucumber-staging.southeastcanopy.com`, enter a staff address, type the emailed code | Cucumber with the *Practice data* banner. `/` is *Page not found* until the app has a home page; that's still Cucumber |
| 2 | Open `/accounts/login/`, log in with a made-up name and password | "Please enter a correct username and password". A 403 here would mean the HTTPS header isn't trusted (design §6.2) |
| 3 | Private tab, an address **not** on `Staff` (e.g. a personal Gmail) | Cloudflare says a code was sent; **none arrives** (inbox and Spam, 3 min) |

Then *Test policies* (A6) works, since the Owner has logged in once.

### Bitwarden entries

All in one Bitwarden folder, **Cucumber**:

| Entry (secure note) | Holds |
|---|---|
| Cucumber staging secrets.env | The whole file from the Asus, incl. the `cucumber-staging` tunnel token. Copy it again after any change: `ssh cucumber-staging 'cat ~/cucumber/staging/secrets.env' \| pbcopy`, paste over the note, then copy any word to clear the clipboard |
| Cloudflare tunnel · cucumber-staging-admin | Token, tunnel ID, route, where it lives (`/etc/cloudflared/admin-tunnel.env`), the re-install command |
| Cloudflare tunnel · cucumber-staging | Tunnel ID only; token is in the `secrets.env` note |
| Cloudflare (login) | Notes: Zero Trust team `southeastcanopy` |

Production gets the same set at step 6.

## Day to day: who can get in

- **Someone joins:** Access controls → Policies → `Staff` → **Configure** →
  add their address to *Emails*.
- **Someone leaves:** remove them from `Staff` (and `Admins`), then Team & Resources → **Users** → that person → **Revoke
  session**. Without the revoke, an open session lasts up to a month.
- Log both in the table below.

## Log

| Date | Step | Result | By |
|---|---|---|---|
| 2026-10-17 | A1 | Zero Trust Free; Cloudflare's random team name changed to `southeastcanopy` | Owner |
| 2026-10-17 | A3 | No Lists: addresses go in the policies (see A3) | Owner, Claude |
| 2026-10-17 | A4 | `Staff` (Allow: `admin@`, `thanapat.s@southeastcanopy.com`), `Admins` (Allow), `Health check` (Bypass, first saved as Allow, fixed) | Owner |
| 2026-10-17 | A5 | Five applications as in the table; `Cucumber Staging SSH` first saved with no policy, `Admins` added. Saving needed *clientless access* and *WARP authentication* off | Owner |
| 2026-10-17 | Admins | Owner approved: `Admins` = Owner's address only | Owner |
| 2026-10-17 | A2 | Account had only the *Cloudflare* provider (new-account default). One-time PIN added; all five apps set to One-time PIN only | Owner |
| 2026-10-17 | Decided | One-time PIN only for now. Microsoft 365 (Entra ID) login considered for later: one place to remove a leaver, but a secret to renew | Owner |
| 2026-10-17 | A6 | Policy tester can't run before a first login (`invalid_user_id`): moved to step 4 | Owner, Claude |
| 2026-10-17 | B1 | `cucumber-staging` and `cucumber-staging-admin` tunnels up, routes added (Asus runbook Phase 7). A mistaken first tunnel (*Cloudflared*) deleted. The new dashboard waits for a connection before the route step; first route attempt was *Private hostname*, cancelled | Owner, Claude |
| 2026-10-17 | B2 | `ssh cucumber-staging-remote hostname` → `cucumber-staging`, arriving from `127.0.0.1` (tunnel). Repeat with the Mac on phone data for AC22 | Owner, Claude |
| 2026-10-17 | B3 | **AC19 (staging) passed:** phone on 5G, email code for `admin@`, Cucumber with the banner; made-up login refused by Cucumber (no 403, no redirect loop). **AC20 passed:** Gmail address got no code | Owner |
| 2026-10-17 | Bitwarden | Entries as in the table above | Owner |
