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

**The export (2026-10-16) also has:**

| Name | Type | Value | Note |
|---|---|---|---|
| `@` | A | `WebsiteBuilder Site` | GoDaddy's placeholder, not an address: Cloudflare and `check_dns.py` can't read it |
| `instagram` | A | `15.197.225.128`, `3.33.251.168` | GoDaddy **forwarding**: redirects to `www.instagram.com` (only works on GoDaddy's nameservers) |
| `pay` | CNAME | `paylinks.commerce.godaddy.com` | GoDaddy Payments pay links |
| `_domainconnect` | CNAME | `_domainconnect.gd.domaincontrol.com` | GoDaddy's set-up helper for other services |
| `_dmarc` | TXT | `v=DMARC1; p=quarantine; …` | Email protection policy |

The export was under the DNS that GoDaddy's domain page called "managed
elsewhere" (it's still GoDaddy's nameservers). **Use the corrected copy**
`~/Documents/southeastcanopy.com.cloudflare.txt` in A4 and A5: the same file
with `WebsiteBuilder Site` replaced by the website's two addresses.

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
   pick `~/Documents/southeastcanopy.com.cloudflare.txt`, and **untick** *Proxy imported
   DNS records*.
3. On the DNS records page, set **every record to DNS only (grey cloud)**,
   including `@` and `www`. Delete any record GoDaddy didn't have (Claude
   checks this with Cloudflare's own export in A5).
4. Write down the **two nameservers Cloudflare assigns** (like
   `xxx.ns.cloudflare.com`). **Don't change anything at GoDaddy yet.**

### A5. Check every record (Claude, 5 min)

From the repo on the Owner's Mac:

```bash
uv run --no-dev python -m scripts.check_dns ~/Documents/southeastcanopy.com.cloudflare.txt \
  --server <one of Cloudflare's two nameservers>
```

- **Use TCP.** The lab and home networks may intercept ordinary (UDP) DNS
  and answer from their own cache, which silently gives GoDaddy's answers.
  Test: `dig +short A example.com @192.0.2.1` must time out. If it answers,
  run the checker over TCP (until `check_dns.py` gets a `--tcp` option):

  ```bash
  uv run --no-dev python -c "import sys, scripts.check_dns as c; c.DIG_OPTIONS = [*c.DIG_OPTIONS, '+tcp']; sys.exit(c.main(sys.argv[1:]))" \
    ~/Documents/southeastcanopy.com.cloudflare.txt --server harlan.ns.cloudflare.com
  ```

- It must end with **all records match**, for both Cloudflare nameservers.
- **Before the switch, the checker can't see proxying:** Cloudflare doesn't
  proxy until the site is active. So the Owner exports Cloudflare's records
  (DNS → Records → *Import and Export* → *Export*) and Claude reads it:
  every line `cf-proxied:false`, **no NS lines other than Cloudflare's own**
  (the import copies GoDaddy's `ns71`/`ns72`; delete them), and no record
  GoDaddy didn't have.
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
| Switched | Claude | `dig +tcp NS southeastcanopy.com @1.1.1.1` shows Cloudflare's two names |
| Records | Claude | `check_dns.py` over TCP (A5) with `--server <Cloudflare nameserver>`, and again with no `--server` |
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
| 2026-10-16 | A2 export | Saved. 9 names; `@` A is GoDaddy's `WebsiteBuilder Site` placeholder (corrected copy made); `instagram` uses GoDaddy forwarding | Owner, Claude |
| 2026-10-16 | Baseline | `check_dns.py` on the corrected copy against `ns71.domaincontrol.com`: all records match | Claude |
| 2026-10-16 | A3.1 DNSSEC | Off ("Turn On DNSSEC" offered) | Owner |
| 2026-10-16 | A3.2 Forwarding | Domain: not set up. Subdomain `instagram` → `https://www.instagram.com` (GoDaddy's free social subdomain, not the profile). **Dropped**: left out of the corrected copy; stops working after the switch | Owner |
| 2026-10-16 | A3.3 Website | Products tab: "You connected a website to southeastcanopy.com", SSL certificate active; no nameserver requirement shown | Owner |
| 2026-10-16 | A3.4 Microsoft 365 | Not bought through GoDaddy (Products tab offers Email "Get Started", none connected) | Owner |
| 2026-10-16 | Noted | GoDaddy **auto-renew is off**, domain expires 2027-09-08: Owner to decide on turning it on | Owner |
| 2026-10-16 | A4 | Site added at Cloudflare (Free); nameservers `harlan.ns.cloudflare.com`, `susan.ns.cloudflare.com` | Owner |
| 2026-10-16 | A5 export 1 | Cloudflare export: 6 records **proxied** (`@` ×2, `www`, `autodiscover`, `pay`, `_domainconnect`) and GoDaddy's `ns71`/`ns72` imported as NS records. Owner set all to DNS only and deleted the two NS records | Owner, Claude |
| 2026-10-16 | A5 export 2 | Every record `cf-proxied:false`, no `domaincontrol.com` NS, no extras: matches GoDaddy's list | Claude |
| 2026-10-16 | **Found** | **This network intercepts DNS over UDP** (a query to unused `192.0.2.1` was answered; "Cloudflare" answers had no `aa` flag). Earlier `--server` runs read GoDaddy's data. Over TCP the real servers answer | Claude |
| 2026-10-16 | A5 (TCP) | `check_dns.py` with `+tcp` against `harlan` and `susan`: **all records match**; against `ns71.domaincontrol.com`: all match. `instagram` already removed at GoDaddy (SOA 2026101600) | Claude |
| 2026-10-16 | **Part A done** | Waiting for Part B on a weekday morning | |
