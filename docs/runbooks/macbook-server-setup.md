# Runbook · Spare MacBook Air as the Cucumber server

**For:** a Claude Code session running **on the spare MacBook**, working with
the Owner (Jade) at the keyboard. **Unit:** U0.4 host set-up, plus U0.1 G5
(spike on the real host, checked on an Android phone).
**Background:** [ADR-0001 › Hosting](../roadmap/adr/0001-stack-selection.md#hosting)
and its [set-up checklist](../roadmap/adr/0001-stack-selection.md#set-up-checklist-u04).

## Rules for the session running this

- **Explain each step in plain words before doing it.** The Owner is newer to
  development and wants to understand what changes on the Mac.
- **Anything needing `sudo`:** show the command and ask the Owner to run it
  with the `!` prefix, typing their own password. Never ask for the password.
- **Never** erase the Mac, turn FileVault off, change the admin password or
  install anything not listed here **without the Owner saying yes first**.
- **Never** put passwords, tokens or webhook addresses in files, commits or
  chat. Secrets go into the Owner's password manager or GitHub secrets.
- GUI-only settings: tell the Owner exactly where to click, then check the
  result with the terminal command given.
- **Stop at the end of Phase 2.** Phase 3 needs decisions from the main
  planning session.
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
runs it with `!`):

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

## Setup log

Fill this in as you go, then commit and push it (last step).

| Item | Result |
|---|---|
| Date | |
| macOS version | |
| Chip / memory / free disk | |
| Battery condition / max capacity / cycles | |
| Erased first? | |
| Admin account name | |
| Charge limit 80 % | |
| Sleep on power off (`pmset -g`) | |
| macOS auto-install off | |
| FileVault (on / off, Owner's choice) | |
| Automatic login (only if FileVault off) | |
| Hostname | |
| Firewall | |
| SSH / Screen Sharing | |
| Network (Ethernet / Wi-Fi), IP address | |
| Docker Desktop version, starts at login | |
| Spike tests (expect 18 passed) | |
| iPhone 13 test | |
| Android test (model) | |
| Restart test | |
| Problems or open questions | |

**Last step:** commit the filled-in log on the spike branch and push it, so
the main session can read it:

```bash
git add docs/runbooks/macbook-server-setup.md
git commit -m "docs: record MacBook server setup log"
git push
```
