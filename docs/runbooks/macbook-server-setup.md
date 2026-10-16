# Runbook · Spare MacBook Air as the Cucumber server

**For:** a Claude Code session running **on the spare MacBook**, working with
the Owner (Jade) at the keyboard. **Unit:** U0.4 host set-up, plus U0.1 G5
(spike on the real host, checked on an Android phone).
**Background:** [ADR-0001 › Hosting](../roadmap/adr/0001-stack-selection.md#hosting)
and its [set-up checklist](../roadmap/adr/0001-stack-selection.md#set-up-checklist-u04).

## Rules for the session running this

- **Explain each step in plain words before doing it.** The Owner is newer to
  development and wants to understand what changes on the Mac.
- **Anything needing `sudo`** (including `brew install --cask`): show the
  command and ask the Owner to run it in the **Terminal app**, typing their
  own password. The `!` prefix has no terminal for `sudo` to ask in, so it
  fails. Never ask for the password.
- **Never** erase the Mac, turn FileVault off, change the admin password or
  install anything not listed here **without the Owner saying yes first**.
- **Never** put passwords, tokens or webhook addresses in files, commits or
  chat. Secrets go into the Owner's password manager or GitHub secrets.
- GUI-only settings: tell the Owner exactly where to click, then check the
  result with the terminal command given.
- **Stop at the end of Phase 2.** Phase 3 needs decisions from the main
  planning session. (Phase 3 is now written: it runs from the Owner's Mac
  over SSH, not in a session on this MacBook.)
- At the end, fill in the [Setup log](#setup-log) and push it (see the last
  step).

## Phase 0 · Facts to check first

```bash
sw_vers                                    # macOS version (need 26.4+ for charge limit)
system_profiler SPHardwareDataType | grep -E "Model Name|Chip|Memory"
system_profiler SPPowerDataType | grep -E "Cycle Count|Condition|Maximum Capacity"
df -h / | tail -1                          # free disk
fdesetup status                            # FileVault on or off
```

Record the results in the Setup log. Expected: MacBook Air, Apple M2, 8 GB.

## Phase 1 · macOS basics

| # | Step | Where (GUI) | Check |
|---|---|---|---|
| 1 | **Fresh start?** Only if the Owner wants it and has backed up: erase. Otherwise skip | General → Transfer or Reset → Erase All Content and Settings | — |
| 2 | Update to the newest macOS 26 (≥ 26.4) | General → Software Update | `sw_vers` |
| 3 | One admin account (e.g. `cucumber-admin`) with a strong password, saved in the Owner's password manager | Users & Groups | `id -un` |
| 4 | Time zone Bangkok, time set automatically | General → Date & Time | `sudo systemsetup -gettimezone` |
| 5 | Battery **charge limit 80 %** | Battery → Charging | Owner confirms on screen |
| 6 | **Never sleep on power**; display may turn off | Battery → Options → "Prevent automatic sleeping on power adapter when the display is off" | `pmset -g` shows `sleep 0` on AC |
| 7 | Updates: download yes, **install macOS updates no**, security responses yes | General → Software Update → ⓘ Automatic updates | `defaults read /Library/Preferences/com.apple.SoftwareUpdate` |
| 8 | **FileVault: Owner decides.** On = data safe if stolen, but someone types the password after an unplanned restart. Off = restarts unattended, data readable if stolen; then also turn on automatic login | Privacy & Security → FileVault | `fdesetup status` |
| 9 | Name the Mac `cucumber-server` | General → Sharing → Local hostname → Edit | `scutil --get LocalHostName` |
| 10 | Firewall on | Network → Firewall | `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` |
| 11 | Remote Login (SSH) and Screen Sharing on, **admin account only** | General → Sharing | `nc -z localhost 22 && echo ssh-on` |
| 12 | Network: USB-C Ethernet if available, else 5 GHz Wi-Fi | — | `networksetup -listallhardwareports` and `ipconfig getifaddr en0` |
| 13 | Quiet it down: notifications off, Siri off, unknown Login Items removed | Notifications · Siri · General → Login Items | Owner confirms |
| 14 | **Lid stays open.** A closed MacBook sleeps whatever the settings say | — | — |

The terminal equivalent of step 6, if the GUI option is missing (the Owner
runs it in the Terminal app):

```bash
sudo pmset -c sleep 0 disksleep 0 displaysleep 10 womp 1
```

## Phase 2 · Tools and the spike

1. **Homebrew:** follow the current command at <https://brew.sh> and show it to
   the Owner before running it.
2. **Tools:**
   ```bash
   brew install git gh uv
   brew install --cask docker-desktop    # Docker Desktop; free for a business under 250 staff and US$10M revenue
   ```
   If the cask name has changed, use `brew search docker` and confirm with the
   Owner.
3. **Docker Desktop settings:** open it, accept the terms, then Settings →
   General → **Start Docker Desktop when you sign in** on; Resources → Memory
   **4 GB**. Check with `docker info --format '{{.ServerVersion}}'`.
4. **The spike** is already here: this runbook came from the
   `spike/u0.1-ui-kit` branch, so the code is in the `spike/` folder of the
   same checkout.
   ```bash
   cd spike                          # from the repo root
   docker compose up -d --wait
   uv sync
   uv run pytest -q                   # expect 18 passed
   uv run python manage.py migrate
   uv run python manage.py createsuperuser   # the Owner types username and password
   uv run python manage.py runserver 0.0.0.0:8000
   ```
5. **Allow incoming connections:** if macOS asks whether Python may accept
   incoming network connections, the Owner clicks **Allow**.
6. **Phone test (U0.1 G5):** on the **same Wi-Fi**, open
   `http://<address from ipconfig getifaddr en0>:8000/daisy/` on the Owner's
   **iPhone 13** and on an **Android** phone. Log in, save one entry, and try
   quantity 0 to see the error. Note the Android model and anything odd.
7. **Restart test:** with the Owner's OK, restart the Mac. Check that it comes
   back on its own (or waits for the FileVault password, as expected), and that
   Docker Desktop starts by itself (`docker info`). The spike's dev server
   doesn't auto-start; that's fine for now. The real app gets a proper service
   in U0.4.

**Stop here.** Phase 3 (Cloudflare Tunnel + Access, so staff can reach it away
from this Wi-Fi) waits for the Owner's answer on a domain name, and is planned
in the main session.

## Phase 3 · Production copy (Claude over SSH, ~30 min)

**For:** Claude in a session on the Owner's Mac, with the Owner next to the
MacBook. U0.4a G6 needs it ([G6 plan](../roadmap/units/u0.4a-g6-release.md));
U0.4b design §10.1 planned it. **The tunnel stays off:** production answers on
the MacBook only, until U0.4b adds the tunnels, the admin tunnel and the
uptime check (§6, §8, §9). Production holds **no real data until R1 go-live**.

### 3.1 SSH from the Owner's Mac (Owner, 2 min)

On the same Wi-Fi as the MacBook, on the Owner's Mac:

```bash
ssh-copy-id sawat@<MacBook address>          # asks for sawat's password once
```

Then Claude adds to the Mac's `~/.ssh/config` and checks with
`ssh cucumber-server hostname`:

```text
Host cucumber-server
    HostName <MacBook address>
    User sawat
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

### 3.2 Set-up script (Claude; Owner adds the deploy key)

```bash
scp deploy/setup-production.sh cucumber-server:
ssh cucumber-server bash setup-production.sh
```

| # | Step | Why |
|---|---|---|
| 1 | Checks git, uv and Docker Desktop, and that Docker can pull an image over SSH | Phases 1–2 installed them; this only checks |
| 2 | Ports 8000 and 5436 free (the old spike's dev server used 8000) | Production's app and database ports (U0.4a §3) |
| 3 | Its own **read-only deploy key**, used only through the `github-cucumber` alias, so `sawat`'s own GitHub access is untouched. First run: it prints the public key and stops | The repo is private. Owner adds it at GitHub → Settings → **Deploy keys**, "Allow write access" **unticked**, then Claude runs the script again |
| 4 | `~/cucumber/production/{backups,logs}`, private to `sawat` | Design §6.1 |
| 5 | Clones `~/cucumber/tools` (stays on `main`, runs the scripts) and `~/cucumber/production/src` (what gets built) | Design §6.1; G5 finding 3 |
| 6 | `secrets.env` made **on the MacBook** by `scripts.make_secrets production`: production's name, ports 8000/5436, memory caps 1g/1536m/128m (U0.4b Q3), HSTS 3600, tunnel off, new random secrets. `chmod 600`, never overwritten, values never printed | Production's keys differ from staging's by construction (U0.4a G4). The script prints each secret's fingerprint (first 8 characters of its SHA-256) for the log |
| — | Prints versions, Docker memory, free disk, sleep, firewall, FileVault | For the Phase 3 log below |

**If docker can't pull over SSH** (step 1 stops): Docker Desktop keeps
logins in the macOS keychain, which an SSH session may not be able to open,
even for public images. Either the Owner runs
`security unlock-keychain ~/Library/Keychains/login.keychain-db` in an
`ssh -t cucumber-server` session (typing `sawat`'s password), or, with the
Owner's OK, remove the `"credsStore": "desktop"` line from
`~/.docker/config.json` on the MacBook (Cucumber only pulls public images).

### 3.3 Secrets into Bitwarden (Owner, 3 min)

At the MacBook, in the Terminal app: `cat ~/cucumber/production/secrets.env`.
Copy the whole text into a new Bitwarden secure note named **Cucumber
production secrets.env**, as was done for staging. Then clear the Terminal
window (⌘K). Restoring production from a copy needs these values.

### 3.4 First deploy

Production's first deploy is the first release: follow the
[release runbook](release.md). Until then production is set up but not
running.

### 3.5 Restart test (with the Owner's OK, after the first deploy)

Restart the MacBook; the Owner types the FileVault password at the start-up
screen and logs in as `sawat` (Docker Desktop starts at login, not before).
Then, with no other step, `/health/` answers (release runbook, step 6). The
tunnel part of the test (AC24) comes with U0.4b.

### Phase 3 log

| Item | Result |
|---|---|
| Date | |
| SSH from the Owner's Mac (`ssh cucumber-server hostname`) | |
| Deploy key added (read-only), title | |
| Script output: macOS, Docker, Compose, uv, Docker memory | |
| Free disk / sleep / firewall / FileVault | |
| Secret fingerprints: production (compare with staging's) | |
| Secrets saved in Bitwarden | |
| Restart test | |
| Problems | |

## Setup log

Fill this in as you go, then commit and push it (last step).

| Item | Result |
|---|---|
| Date | 2026-10-11 |
| macOS version | 15.7.7 (24G720) at start; updated to 27.0.1 (26A434) |
| Chip / memory / free disk | Apple M2 / 8 GB / 25 GB free of 228 GB |
| Battery condition / max capacity / cycles | Normal / 87 % / 205 |
| Erased first? | No |
| Admin account name | `sawat` (existing admin, Owner chose not to add `cucumber-admin`) |
| Charge limit 80 % | Set to 90 % (Owner's choice) |
| Sleep on power off (`pmset -g`) | Yes, `sleep 0` on AC; display sleeps after 10 min |
| macOS auto-install off | Yes; downloads and security responses still on |
| FileVault (on / off, Owner's choice) | On. After a restart, type `sawat`'s password at the startup screen |
| Automatic login (only if FileVault off) | Not applicable |
| Hostname | `cucumber-server` |
| Firewall | On |
| SSH / Screen Sharing | Both on, Administrators only (`sawat`) |
| Network (Ethernet / Wi-Fi), IP address | Wi-Fi 5 GHz (ch 36, -61 dBm), 192.168.101.12; no Ethernet adapter yet |
| Docker Desktop version, starts at login | Desktop 4.94.0, Engine 29.8.2, 4 GB memory; starts at login (confirmed in restart test) |
| Spike tests (expect 18 passed) | 18 passed |
| iPhone 13 test | Worked: login, saved an entry, quantity 0 rejected (daisyUI) |
| Android test (model) | vivo Y3s (V2044), Funtouch OS 12, 3 GB RAM, Chrome: login first showed **403 CSRF** (see Problems); works after the double-tap fix |
| Restart test | Passed. Restarted 23:02; waited for the FileVault password as expected, then Docker Desktop started by itself (23:03, `docker info` OK). SSH, firewall, `sleep 0` and the IP address unchanged. The spike's `db` container stayed stopped (no `restart:` policy in `compose.yaml`); `docker compose up -d --wait` brought it back with the user and the saved entry intact. The real app's service in U0.4 needs to start its database on boot |
| Problems or open questions | Android login sent 4 POSTs in the same second (repeat taps on a slow phone). The 1st logged in and rotated the CSRF token, so the later ones got 403 "CSRF token from POST incorrect". The spike has no double-submit guard on login or on entry Save; on append-only entries a double tap would save a duplicate that can't be removed. Spike now has the button guard; real-app work tracked in #4 |

**Last step:** commit the filled-in log on the spike branch and push it, so
the main session can read it:

```bash
git add docs/runbooks/macbook-server-setup.md
git commit -m "docs: record MacBook server setup log"
git push
```
