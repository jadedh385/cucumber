# Runbook · Cloudflare Zero Trust: Access, tunnels, SSH, uptime

**For:** the Owner, with Claude checking from the Owner's Mac. **Why:** U0.4b
AC19–AC23 ([design §6–§9](../roadmap/units/u0.4b-design.md#7-access-the-email-check-ac19-ac20)).
This is step 2 of the design's order of work (§12): the account, the email
lists and the Access applications. Tunnels (steps 4 and 6) are added to this
runbook when their turn comes.

**What it changes:** nothing anyone can see yet. No name points at a tunnel,
so the Access applications guard addresses that don't answer. Email, the
website and the DNS records are not touched.

**Time:** about 45 minutes, any day, in the browser only.

**Menu names.** Cloudflare renames Zero Trust menus often. If a menu below
isn't there, use the dashboard's search box with the last word (e.g.
*Lists*, *Login methods*).

## Part A · Account, lists and Access

### A1. Zero Trust account (Owner, 10 min)

`dash.cloudflare.com` → left menu **Zero Trust**.

- **Team name:** `southeastcanopy`. The login page becomes
  `southeastcanopy.cloudflareaccess.com`.
- **Plan:** **Free** (up to 50 people). Cloudflare may ask for a card;
  nothing is charged on Free.
- Save the team name in the Bitwarden entry for Cloudflare (notes).

### A2. Login method (Owner, 2 min)

Settings → Authentication → **Login methods**.

- **One-time PIN** is listed (Cloudflare adds it by default). If not: *Add
  new* → One-time PIN.
- Add no other method (design §7: email code only).

### A3. Email lists (Owner, 5 min)

Reusable components → **Lists** → *Create manual list*, type **Emails**.

| List | Entries now |
|---|---|
| `Cucumber staff` | The Owner's work address. Staff addresses can be added now or before they first use Cucumber |
| `Cucumber admins` | The Owner's work address only |

Type each address in lower case, exactly as the person's mailbox spells it.

### A4. Policies (Owner, 5 min)

Access controls → **Policies** → *Add a policy*. Three reusable policies:

| Policy name | Action | Include | Session |
|---|---|---|---|
| `Staff` | Allow | *Emails in list* → `Cucumber staff` | Same as application |
| `Admins` | Allow | *Emails in list* → `Cucumber admins` | Same as application |
| `Health check` | **Bypass** | *Everyone* | — |

### A5. Access applications (Owner, 15 min)

Access controls → **Applications** → *Add an application* → **Self-hosted**.
One per row. Under *Public hostname*: subdomain, then `southeastcanopy.com`,
then the path (blank unless shown).

| Application name | Subdomain | Path | Policy | Session duration |
|---|---|---|---|---|
| `Cucumber` | `cucumber` | — | `Staff` | 1 month |
| `Cucumber health` | `cucumber` | `health/` | `Health check` | (default) |
| `Cucumber staging` | `cucumber-staging` | — | `Staff` | 1 month |
| `Cucumber SSH` | `cucumber-ssh` | — | `Admins` | 24 hours |
| `Staging SSH` | `cucumber-staging-ssh` | — | `Admins` | 24 hours |

On each application:

- **Login methods:** only *One-time PIN*; turn on **Instant Auth** if offered
  (skips the "choose a method" page).
- A warning that the name has **no DNS record** is expected: the tunnels add
  the records later. Save anyway.
- Leave the *App Launcher* off.

`Cucumber health` covers only `/health/` and anything under it (design §7).
Access uses the most specific match, so the rest of `cucumber.…` still asks
for the code.

### A6. Checks (Owner and Claude, 5 min)

| Check | Who | How |
|---|---|---|
| Login page | Claude | `curl -sI https://southeastcanopy.cloudflareaccess.com` answers (not a DNS error) |
| Policy test | Owner | In `Cucumber`'s policies, *Test policies* (if offered): the Owner's address is **allowed**; a personal Gmail is **blocked** |
| Setup | Owner | Screenshot of the Applications list, the two Lists and Login methods, for Claude to compare with A3–A5 |

The real AC19/AC20 test (a phone gets a code, a stranger doesn't) needs a
tunnel. It runs at step 4 (staging) and step 6 (production).

### A7. Uptime account (Owner with Claude, later)

Picked at sign-up after reading the free plan's terms (design §9, Q2). It
only watches production, so it can wait until step 6.

### Undo

Delete the applications, policies and lists. Nothing points at them yet.

## Day to day: the staff list

- **Someone joins:** Lists → `Cucumber staff` → add their address.
- **Someone leaves:** remove them from `Cucumber staff` (and `Cucumber
  admins`), then Team & Resources → **Users** → that person → **Revoke
  session**. Without the revoke, an open session lasts up to a month.
- Log both in the table below.

## Log

| Date | Step | Result | By |
|---|---|---|---|
| | A1 | | |
