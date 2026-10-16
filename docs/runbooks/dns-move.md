# Runbook · Moving the DNS from GoDaddy to Cloudflare

**For:** the Owner, with Claude checking from the Owner's Mac. **Why:** U0.4b
AC15 and AC16 ([design §4–§5](../roadmap/units/u0.4b-design.md#4-the-dns-move-ac15-ac16)).
The tunnels and Access (U0.4b step 2 onwards) need the domain's records to
live at Cloudflare.

**What moves:** only the list of records (the "DNS"). The domain stays
registered and paid for at GoDaddy, Microsoft 365 email stays at Microsoft,
the website stays on GoDaddy Websites + Marketing.

**Time:** Part A about 45 minutes, any day. Part B 10 minutes plus watching
email for the rest of that day. Part A changes nothing for anyone; Part B
is the switch.

## What the domain has today (2026-10-16, public look-up)

| Name | Type | Value | Used by |
|---|---|---|---|
| `@` | NS | `ns71.domaincontrol.com`, `ns72.domaincontrol.com` | GoDaddy (changes in Part B) |
| `@` | A | `76.223.105.230`, `13.248.243.5` | Website |
| `www` | CNAME | `southeastcanopy.com` | Website |
| `@` | MX | `0 southeastcanopy-com.mail.protection.outlook.com` | Email in |
| `@` | TXT | `v=spf1 include:spf.protection.outlook.com -all` | Email out (SPF) |
| `@` | TXT | `v=verifydomain MS=3030835` | Microsoft 365 domain check |
| `autodiscover` | CNAME | `autodiscover.outlook.com` | Outlook set-up |

- **DNSSEC is off** (no DS record), so no 2-day wait is needed (design §4.1
  step 2). Still confirm it on GoDaddy's page in A3.
- **No DKIM records** (`selector1._domainkey`, `selector2._domainkey`). Not
  needed for the move. Turning DKIM on in Microsoft 365 afterwards helps
  email stay out of spam: logged for later (design §16).
- The zone file export (A2) is the real list; this table is only what a
  look-up from outside can guess.

## Part A · Before the switch (nothing changes yet)

### A1. Lock down both accounts (Owner, 10 min)

On **GoDaddy** and on **Cloudflare** (sign up at `dash.cloudflare.com` if
there's no account yet, free plan):

- Two-step login with an **authenticator app**, not SMS.
- Recovery codes saved in **Bitwarden**.
- GoDaddy → Domain → *Domain lock*: stays **on**.
- The Owner is the only member of the Cloudflare account.

### A2. Export the records from GoDaddy (Owner, 5 min)

GoDaddy → My Products → `southeastcanopy.com` → DNS → *Export zone file*
(under the "…" or Actions menu).

- Save it as `~/Documents/southeastcanopy.com.txt`, **not in the repo**.
- Also take a screenshot of the whole DNS records page and keep it with it.

Tell Claude when it's saved; Claude reads it and compares it with the table
above.

### A3. GoDaddy checks (Owner, 5 min)

Note each answer in the log at the bottom:

1. **DNSSEC:** Domain → DNSSEC. Expected **off**. If on: stop, tell Claude
   (turn it off and wait 2 days).
2. **Forwarding:** Domain → *Forwarding*. Expected **none** on `@` or `www`.
   If set: stop, decide with Claude (it only works on GoDaddy's nameservers).
3. **Website:** Websites + Marketing → Settings → domain. If it says the
   domain **must** use GoDaddy's nameservers: stop (fallback: a new domain at
   Cloudflare, about US$10/year, design §4.1 step 6).
4. **Microsoft 365:** was it bought **through GoDaddy** (it shows under My
   Products as "Microsoft 365 from GoDaddy")? If yes: stop, tell Claude.
   GoDaddy then stops managing its records after the switch, and its own
   guidance must be read first.

### A4. Add the site at Cloudflare (Owner, 10 min)

1. Cloudflare → *Add a domain* → `southeastcanopy.com` → **Free** plan.
2. When it offers to scan or import records: choose **import a zone file**,
   pick `~/Documents/southeastcanopy.com.txt`, and **untick** *Proxy imported
   DNS records*.
3. On the DNS records page, set **every record to DNS only (grey cloud)**,
   including `@` and `www`. Delete any record GoDaddy didn't have (Claude
   checks this with Cloudflare's own export in A5).
4. Write down the **two nameservers Cloudflare assigns** (like
   `xxx.ns.cloudflare.com`). **Don't change anything at GoDaddy yet.**

### A5. Check every record (Claude, 5 min)

From the repo on the Owner's Mac:

```bash
uv run --no-dev python -m scripts.check_dns ~/Documents/southeastcanopy.com.txt \
  --server <one of Cloudflare's two nameservers>
```

- It must end with **all records match**. A `different` on `@` or `www` with
  "is it set to DNS only?" means a cloud is still orange.
- The Owner also exports Cloudflare's records (DNS → Records → *Export*) and
  Claude compares it line by line with GoDaddy's: any extra is deleted.
- Save the output in the log: it is AC15's evidence.

## Part B · The switch

**When:** a weekday morning the Owner can watch email for the rest of the day.

### B1. Change the nameservers (Owner, 5 min)

GoDaddy → `southeastcanopy.com` → DNS → *Nameservers* → *Change* → *I'll use
my own nameservers* → the two Cloudflare names from A4 → Save.

Cloudflare emails when the site is **Active** (minutes to a few hours, 48 h
at worst). **Delete nothing at GoDaddy for 2 weeks.** During those 2 weeks,
every record change is made at **both** GoDaddy and Cloudflare.

### B2. Same-day checks (Owner and Claude)

| Check | Who | How |
|---|---|---|
| Switched | Claude | `dig NS southeastcanopy.com @1.1.1.1` shows Cloudflare's two names |
| Records | Claude | `check_dns.py` with `--server <Cloudflare nameserver>`, and again with no `--server` |
| Email in | Owner | Send from a personal Gmail to a company address; it arrives |
| Email out | Owner | Reply from Outlook; it arrives at the Gmail, not in spam |
| Outlook | Owner | Opens and syncs on phone and desktop |
| Microsoft 365 | Owner | Admin centre → Settings → Domains → `southeastcanopy.com`: no issues |
| Website | Owner | `southeastcanopy.com` and `www.` load on a phone on mobile data, no certificate warning |

**Next morning:** email again, both ways.

### Undo

If a check fails and the fix isn't clear within an hour: GoDaddy →
Nameservers → *GoDaddy default*. It spreads back over hours (up to 48 h).
Keep the Cloudflare site for at least 48 h after an undo.

## Log

| Date | Step | Result | By |
|---|---|---|---|
| 2026-10-16 | Public look-up | NS at GoDaddy; DNSSEC off (no DS); email = Microsoft 365; no DKIM; website on GoDaddy | Claude |
