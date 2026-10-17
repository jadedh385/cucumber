# Runbook · Asus laptop as the staging server (Ubuntu next to Windows)

**For:** the Owner (Jade) at the Asus for Phases 0–3, then a Claude Code
session on the Owner's Mac for Phases 4–6, over the network.
**Unit:** U0.4a G5 (verify on staging); the staging half of U0.4b's host
set-up comes forward. **Decision:** D-26, changed 2026-10-13: staging runs
on the Asus for good; production stays alone on the MacBook.
**Background:** [U0.4 spec › staging options](../roadmap/units/u0.4-spec.md#staging-host-options-compared-2026-10-12),
[U0.4a design](../roadmap/units/u0.4a-design.md) (§6 deploy, §13, §17).

## The plan in one picture

```
Phase 0  Facts from Windows            Jade    10 min   → send the answers to Claude
Phase 1  Make room, keep Windows       Jade    30–60 min (mostly waiting)
Phase 2  Install Ubuntu next to it     Jade    45 min   (one careful screen)
Phase 3  Connect from the Mac          Jade    10 min
Phase 4  Server set-up over SSH        Claude  ~45 min  (Jade types the password once)
Phase 5  First staging deploy          Claude  ~20 min
Phase 6  U0.4a G5 checks               Claude + Jade    (one sitting, G5 note)
Phase 7  Cloudflare tunnels (U0.4b)    Jade + Claude    ~45 min (dashboard, one sudo script)
```

**Why keep Windows (dual boot):** the disk is split in two. Windows keeps its
part and files; Ubuntu gets a new part made from Windows' free space. When the
laptop starts it runs Ubuntu by default (so staging comes back by itself after
a power cut); Windows can still be picked from the start-up menu.

**What dual boot costs:** staging is off while Windows is running, so use
Windows only now and then (or not at all). Windows 10's security updates end
on 2026-10-13, so keep its use to opening old files, not daily web browsing.

## Rules

- **Stop and ask** whenever a screen doesn't match this runbook. A phone
  photo of the screen is the quickest way to check.
- **Never** delete or format a partition marked `ntfs`, `Windows` or
  `Recovery`. The only thing Ubuntu formats is the new free space.
- **Passwords** go into the password manager, never into chat, files or
  commits. Claude never asks for one; the Owner types it when a command asks.
- The staging database holds **practice data only**. Nothing real goes on
  the Asus.

## Phase 0 · Facts to check in Windows (Jade, 10 min)

Send Claude the answers; they decide some choices in Phases 1–2.

| # | Fact | Where | Write down |
|---|---|---|---|
| 1 | Disk size and free space on C: | File Explorer → This PC | e.g. "465 GB, 210 GB free" |
| 2 | SSD or spinning disk (HDD) | Task Manager (Ctrl+Shift+Esc) → Performance → Disk 0 | "SSD" or "HDD" |
| 3 | Start-up mode | Press Win+R, type `msinfo32`, Enter → **BIOS Mode** and **Secure Boot State** | "UEFI" or "Legacy"; On/Off/Unsupported |
| 4 | Partition style and parts | Win+X → Disk Management → right-click **Disk 0** → Properties → Volumes → **Partition style**. Then count the boxes on the Disk 0 row | "GPT" or "MBR"; e.g. "4 parts: EFI, C:, Recovery, Recovery" |
| 5 | Disk encryption | Start → type `BitLocker` (or Settings → Update & Security → Device encryption) | On / Off / not there |
| 6 | Memory | Settings → System → About → Installed RAM | expect 12 GB |

**Stop points:** less than **70 GB free** on C:; or **MBR with 4 parts
already** (MBR allows only 4, so the installer can't add one). In either
case Claude suggests the next step before going on.

### Results for this Asus (2026-10-13)

750 GB spinning disk (Seagate ST9750420AS, HDD) · **MBR** · **Legacy BIOS**,
no Secure Boot · BitLocker off · 12 GB. Disk 0 already has **4 sections**
(MBR's limit): 1 = 0.1 GB start-up files (active), 2 = C: 292 GB (176 GB
free), 3 = 0.8 GB **Windows recovery** (MBR type 39), 4 = D: 406 GB (360 GB
free, ~45 GB used). D: can shrink by up to 368,714 MB.

**Chosen:** move Windows' repair tools onto C:, delete section 3 (frees the
slot Ubuntu needs), **shrink D: by 120 GB** (C: untouched), Ubuntu in that
space at the end of the disk. Phase 1 below is the generic version;
**this Asus uses [Phase 1 for this Asus](#phase-1-for-this-asus-mbr-4-sections)**.

## Phase 1 for this Asus (MBR, 4 sections)

All in **PowerShell as administrator** unless it says Disk Management.

1. **Back up** what you'd mind losing from C: and D: (D: has ~45 GB).
2. **Fast Startup off** (generic step 4) and `powercfg /h off`.
3. **Repair tools onto C::** `reagentc /disable`. Check: `reagentc /info`
   says *Disabled*, and `Test-Path C:\Windows\System32\Recovery\Winre.wim`
   says **True**. If False: stop and ask.
4. **Delete section 3** with `diskpart`: `select disk 0` → `list partition` →
   `select partition 3` → `detail partition` (**check: Type 27, about
   804 MB; otherwise stop**) → `delete partition override` → `list partition`
   (3 sections left) → `exit`.
5. **Shrink D:** Disk Management → right-click D: → Shrink Volume → amount
   **122880** → Shrink. Check: **120.00 GB Unallocated** after D:.
6. **Repair tools back on:** `reagentc /enable`; `reagentc /info` says
   *Enabled*.
7. **USB stick** (generic step 8) with **Partition scheme MBR, Target system
   BIOS**.

## Phase 1 · Make room, keep Windows (Jade, 30–60 min)

1. **Back up anything you'd mind losing** (to a USB drive or Google Drive).
   Shrinking a disk is normally safe, but not risk-free.
2. **Charger in** for everything that follows.
3. **If BitLocker / device encryption is On:** first save the recovery key
   (Manage BitLocker → Back up your recovery key → save to your Microsoft
   account or print it), then **Suspend protection**. Without this, Windows
   may ask for the 48-digit key after Ubuntu is installed.
4. **Turn off Fast Startup** (it leaves the Windows disk half-locked):
   Control Panel → Power Options → *Choose what the power buttons do* →
   *Change settings that are currently unavailable* → untick **Turn on fast
   startup** → Save.
5. **Turn off hibernation** (frees several GB): Start → type `cmd` →
   right-click → *Run as administrator* → type `powercfg /h off` → Enter.
6. **Shrink C:** Disk Management → right-click **C:** → **Shrink Volume** →
   amount: **81920** MB (80 GB) → Shrink. A black box **Unallocated 80 GB**
   appears. **Leave it unallocated:** don't make a new volume in it.
   - If Windows offers much less than 80 GB: run Disk Cleanup (with *Clean up
     system files*), restart and try again. **60 GB is the minimum** (40 GB
     works, but leaves little room for database copies).
7. **Download** on any computer:
   - **Ubuntu Server 24.04 LTS** from `ubuntu.com/download/server` (~3 GB).
     It's supported until 2029 and Docker supports it.
   - **Rufus** from `rufus.ie` (Windows only; on a Mac, balenaEtcher works the
     same way).
8. **Make the USB stick** (≥ 8 GB; **it gets erased**): open Rufus → Device =
   the stick → Boot selection = the Ubuntu file → **Partition scheme = GPT**
   if Phase 0 #3 said UEFI, **MBR** if it said Legacy → Start → if asked,
   choose *ISO Image mode (Recommended)*. Takes ~10–20 min.

## Phase 2 · Install Ubuntu next to Windows (Jade, ~45 min)

1. **Network cable** from the Asus to the router (Wi-Fi set-up is harder in
   the installer, and a cable is steadier for a server).
2. USB stick in. **Restart** and keep tapping **Esc** → boot menu → pick the
   USB stick (on UEFI it starts with `UEFI:`).
   - Stick not listed: restart, tap **F2** (BIOS set-up) → Boot → turn
     **Fast Boot** off (and *CSM/Launch CSM* on only if Phase 0 said Legacy) →
     Save & Exit (F10). **Secure Boot can stay on**: Ubuntu supports it.
3. Choose **Try or Install Ubuntu Server**.
4. Screens, in order:

| Screen | Choose |
|---|---|
| Language · Keyboard | English · English (US), or your layout |
| Type of install | **Ubuntu Server** (not "minimized") |
| Network | the cable shows an address like `192.168.1.57`: **write it down** |
| Proxy · Mirror | leave blank · leave as is (wait for the mirror test) |
| **Storage** | **see step 5. This is the careful one** |
| Profile | Your name: Jade · Server name: **`cucumber-staging`** · User name: **`staging-admin`** · a strong password → password manager |
| Ubuntu Pro | Skip for now |
| SSH | **tick Install OpenSSH server**; don't import keys |
| Featured snaps | **tick nothing** (Docker comes from Docker's own source in Phase 4) |

5. **Storage screen** (the one that matters). **This Asus (MBR, Legacy):**
   select the **120 GB free space** → Add Partition (all of it, ext4, `/`);
   then select the **disk itself** (ST9750420AS) → **Use As Boot Device**
   (puts the Ubuntu start-up menu on the disk; there is no EFI section).
   Summary: only `/`, new, ext4. Generic steps:
   1. Choose **Custom storage layout** → Done.
   2. Under *Available devices*, find the line **free space ~80 GB**
      (the space from Phase 1 step 6). Select it → **Add GPT Partition**
      (or *Add Partition*) → Size: leave empty (= all of it) → Format:
      **ext4** → Mount: **/** → Create.
   3. **UEFI only:** the small existing **EFI / ESP** partition (100–300 MB,
      `vfat`) must show *used as ESP*, mounted at `/boot/efi`. If it doesn't,
      select it → **Use As Boot Device**. **Don't tick "format" on it**:
      Windows needs what is on it.
   4. Check the summary at the top (*FILE SYSTEM SUMMARY*): **only one line,
      `/`, new, ext4**, plus `/boot/efi` on UEFI. **If any `ntfs` line says
      format or delete: press Back and send Claude a photo.**
   5. Done → *Confirm destructive action* → Continue. (It refers only to the
      new partition.)
6. Wait (10–30 min; longer on a spinning disk) → **Reboot Now** → remove the
   stick when asked.
7. It should start **Ubuntu** (a menu with *Ubuntu* first, then black text and
   a `login:` prompt). Log in as `staging-admin` once, type `ip -4 addr` and
   check the address matches the one you wrote down.
   - **Windows isn't in the menu yet:** expected. Phase 4 adds it. Until then,
     on UEFI tap Esc at start-up and choose *Windows Boot Manager*; **on this
     Asus (Legacy) Windows can't be started until Phase 4**, so do Phase 4
     straight after.
   - **It starts Windows instead of Ubuntu:** tell Claude (it's a boot-order
     setting in F2 → Boot).

## Phase 3 · Connect from the Mac (Jade, 10 min)

1. **Router (can wait until Phase 6):** give the Asus a fixed address (often
   called *DHCP reservation* or *Address reservation*), so its address never
   changes. Claude helps find the page for your router model.
2. On the Mac, in the **Terminal app** (replace the address):
   ```bash
   ssh-copy-id staging-admin@192.168.1.57
   ```
   Type `yes` if asked about the fingerprint, then the Ubuntu password once.
   From now on the Mac logs in with its key, with no password.
3. Tell Claude it's done. Claude adds a short name, `cucumber-staging`, to the
   Mac's SSH settings, and checks it with `ssh cucumber-staging hostname`.

## Phase 4 · Server set-up over SSH (Claude, ~45 min)

Claude writes one set-up script, explains it, copies it to the Asus, and the
Owner runs it once in the Terminal app so they can type the password for
`sudo`:

```bash
ssh -t cucumber-staging sudo bash setup-staging.sh
```

What it does, step by step:

| # | Step | Why |
|---|---|---|
| 1 | Update Ubuntu; **automatic security updates**, restart at 04:00 if needed | No one has to remember updates |
| 2 | Time zone **Asia/Bangkok** | Copy names and logs match the MacBook |
| 3 | **Lid closed = keep running**; sleep and hibernate off | A laptop sleeps when its lid closes |
| 4 | **Firewall:** only SSH, only from the home network | Staging is reached through SSH (and later Cloudflare), not an open port |
| 5 | SSH: **keys only**, password login off | After Phase 3 works |
| 6 | **Docker Engine + Compose** from Docker's own source; starts at boot; `staging-admin` may use it | Runs the staging copy |
| 7 | `git` and **uv** | The deploy command runs with `uv run --no-dev` |
| 8 | **Start-up menu:** Ubuntu first (default), Windows listed, 5-second wait | After a power cut it comes back as staging by itself |
| 9 | Windows clock fix note: Ubuntu keeps the hardware clock in UTC; if Windows shows the wrong time, let Windows sync time online (Settings → Time → Sync now) | Dual-boot side effect |

Then, without `sudo`:

10. **GitHub read-only key** (the repo is private): Claude makes a key on the
    Asus and shows the public half; the Owner adds it at GitHub → repo →
    Settings → **Deploy keys** → Add, **"Allow write access" unticked**.
11. **Folders** (design §6.1): `~/cucumber/staging/` with `src/` (the clone),
    `backups/`, `logs/`; `~/cucumber/staging/secrets.env` made from
    `deploy/secrets.env.example`, with `DJANGO_ENVIRONMENT=staging` and new
    random values made **on the Asus** (never shown in chat), `chmod 600`.
    Public host name for now: `cucumber-staging.southeastcanopy.com` (the
    Cloudflare route comes in U0.4b; the health check uses it as the Host).
12. **Restart test:** `sudo reboot`, then check the Asus comes back by itself
    and Docker is running (no keyboard needed, unlike FileVault on the Mac).

## Phase 5 · First staging deploy (Claude, ~20 min)

```bash
ssh -t cucumber-staging
git clone git@github.com:jadedh385/cucumber.git ~/cucumber/tools   # once
cd ~/cucumber/tools && git pull
uv run --no-dev python -m scripts.deploy staging main
```

The scripts run from `~/cucumber/tools`, a clone that stays on `main`
(design §6.1), never from `staging/src`: a tag deploy checks out older code in
`src`, the deploy script included. Type the commands in an SSH session:
`ssh cucumber-staging 'uv …'` on its own finds no `uv` (it lives in
`~/.local/bin`, which only a login shell adds); wrap one-off commands in
`bash -lc '…'`.

Expected: the step lines, then `Done: staging now runs main-<commit>`. The
first build is slow on an old laptop (5–10 min on a spinning disk); later
ones reuse the cache. Then `/health/` says ok and the login page shows the
*Practice data* banner, checked from the Mac through an SSH tunnel:

```bash
ssh -N -L 8001:127.0.0.1:<APP_PORT> cucumber-staging   # then open http://localhost:8001
```

(The app listens only on the Asus itself, by design; the tunnel brings it to
the Mac. Phones reach it once Cloudflare is set up in U0.4b.)

## Phase 6 · U0.4a G5 checks (Claude + Jade)

Recorded in the [G5 note](../roadmap/units/u0.4a-g5-verify.md) (2026-10-16,
with the restore steps), as for U0.2a/b:

- **Deploy and refusals on the real host** (AC10–AC12): step lines and log
  file, a second deploy says "no changes", a failed deploy puts the previous
  build back, tags-only for production checked by command.
- **Practice banner** on login, 404 and 500 pages, at 375 px and desktop
  (AC9; screenshots through the tunnel).
- **Flags** switched with `scripts.flag` as the app user, seen on the next
  request (AC13).
- **Restore rehearsal** (G4 follow-up): write the exact restore steps, then
  restore a saved copy into staging and check the app and the data.
- **Release rehearsal** (AC27): deploy a version, then the previous one back.
- **Sandbox data + walk-throughs** `uat/u0_2a.sh` and `uat/u0_2b.sh` on
  staging, same results as locally (AC26, 65/65 and 42/42).
- **Full E2E suite against staging** through the tunnel (AC25).
- **Timings** on the Asus: deploy time, and the 10× data check from U0.2.
- **Owner sign-off.**

## Phase 7 · Cloudflare tunnels (U0.4b, Jade + Claude, ~45 min)

Two tunnels ([U0.4b design §6.1, §8](../roadmap/units/u0.4b-design.md#61-four-tunnels-one-job-each)),
made in the dashboard (`one.dash.cloudflare.com` → Zero Trust → **Networks →
Tunnels** → *Create a tunnel* → **Cloudflared**). Tokens never go in chat:
each is pasted at a hidden prompt on the Asus and saved in Bitwarden
([list](cloudflare-access.md#bitwarden-entries)).

**The dashboard waits for the tunnel to connect** before it offers the route
step. So: name the tunnel, copy only the long `eyJ…` token from the install
screen (don't run Cloudflare's command), start it on the Asus, then come back
and add the route.

| Tunnel | Install screen | Started by | Route (type **Published application**) |
|---|---|---|---|
| `cucumber-staging` | Docker | `tunnel` service in staging's compose project | `cucumber-staging` . `southeastcanopy.com` → **HTTP** `http://app:8000` |
| `cucumber-staging-admin` | Debian | systemd service `cucumber-admin-tunnel`, outside Docker | `cucumber-staging-ssh` . `southeastcanopy.com` → **SSH** `ssh://localhost:22` |

- **Not *Private hostname*:** that one needs Cloudflare's device app on every
  phone. Staff use a plain browser.
- **`app`, not `localhost`, for the app tunnel:** it runs in its own
  container, where `localhost` is the tunnel itself. The SSH tunnel runs on
  the Asus, so there `localhost` is right.
- The route adds its own DNS record. Check the record's tunnel ID matches
  the tunnel the Asus runs (step 3).

**1. App tunnel token** (Terminal app on the Mac; paste at the prompt):
```bash
ssh -t cucumber-staging 'read -rsp "Token: " t; echo; cd ~/cucumber/staging && sed -i "s|^TUNNEL_TOKEN=.*|TUNNEL_TOKEN=$t|; s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES=tunnel|" secrets.env && echo saved'
```
Then Claude deploys the same version again (`scripts.deploy staging main`);
compose reads `COMPOSE_PROFILES` from `secrets.env` and starts `tunnel`.

**2. Admin tunnel** with [`deploy/setup-staging-admin-tunnel.sh`](../../deploy/setup-staging-admin-tunnel.sh)
(Claude copies it to the Asus; the Owner types the Ubuntu password, then
pastes the token):
```bash
scp deploy/setup-staging-admin-tunnel.sh cucumber-staging:
ssh -t cucumber-staging sudo bash setup-staging-admin-tunnel.sh
```
It installs `cloudflared` from Cloudflare's apt source, adds Docker's and
Cloudflare's sources to automatic updates, keeps the token in
`/etc/cloudflared/admin-tunnel.env` (root only) and runs the tunnel as a
throwaway user with no powers. Not `cloudflared service install <token>`:
that leaves the token in a unit file anyone on the Asus can read.

**3. Checks** (Claude):
- Token's tunnel ID = the route's DNS record (prints the ID, never the token):
  `grep ^TUNNEL_TOKEN= secrets.env | cut -d= -f2- | base64 -d | python3 -c 'import json,sys; print(json.load(sys.stdin)["t"])'`
- `docker logs cucumber-staging-tunnel-1` and
  `journalctl -u cucumber-admin-tunnel`: four *Registered tunnel connection*
  lines each.
- `curl -sI https://cucumber-staging.southeastcanopy.com/` → 302 to
  `southeastcanopy.cloudflareaccess.com` (Access is in front).

**4. SSH from away** (Mac, once): `brew install cloudflared`, then in
`~/.ssh/config`:
```
Host cucumber-staging-remote
    HostName cucumber-staging-ssh.southeastcanopy.com
    User staging-admin
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ProxyCommand /opt/homebrew/bin/cloudflared access ssh --hostname %h
```
`ssh cucumber-staging-remote hostname` opens the browser for the email code
the first time; then plain SSH for 24 hours. On the Asus, such a login comes
from `127.0.0.1` (through the tunnel), not the Wi-Fi.

**5. Phone and HSTS:** the AC19/AC20 phone test is in the
[Access runbook](cloudflare-access.md#b3-phone-test-ac19-ac20). Once it
passes, `DJANGO_HSTS_SECONDS=604800` in `secrets.env` and the same version
deployed again (design §6.3); 31536000 after two weeks with no HTTPS trouble.

**6. Restart test (AC24):** `ssh -t cucumber-staging sudo reboot`; no
keyboard; within a few minutes `cucumber-staging.…` loads on a phone on
mobile data and `ssh cucumber-staging-remote hostname` works.

## If something goes wrong

| Problem | What to do |
|---|---|
| Windows asks for a BitLocker key | Type the recovery key saved in Phase 1 step 3 |
| The laptop starts Windows only | F2 → Boot → put *ubuntu* first; or tell Claude |
| The installer shows no free space | Phase 1 step 6 didn't leave it unallocated; go back to Windows and check Disk Management |
| Ubuntu doesn't work out at all | In Windows Disk Management, delete the Ubuntu partition and *Extend* C: into the space; Windows is untouched. Claude helps remove the leftover Ubuntu start-up entry |
| Old battery swells or won't hold charge | Unplug, stop using it, and tell Claude. The battery is optional (it covers short power cuts) |

## Setup log

| Date | Phase | Result | Who |
|---|---|---|---|
| 2026-10-13 | 0 | Facts above; D: shrinkable by 368,714 MB. Plan: delete recovery section, shrink D: by 120 GB | Jade + Claude |
| 2026-10-13 | 1 | Fast Startup and hibernation off; Winre.wim confirmed on C: (hidden, so `Test-Path` said False; `Get-ChildItem -Force` found it); recovery section removed with `Remove-Partition` (diskpart wouldn't start in that window); D: shrunk to 285.67 GB; **120.00 GB unallocated** at the end (plus 805 MB left unused where section 3 was); Windows RE enabled again on C: (`partition2\Recovery\WindowsRE`). Next: install media | Jade + Claude |
| 2026-10-15 | 1 | Install media: first card failed (hardware); new 128 GB USB stick written on the Mac with `dd` from `ubuntu-26.04.1-live-server-amd64.iso` (SHA-256 matches Ubuntu's SHA256SUMS; ISO has Legacy BIOS boot files). Next: Phase 2 | Jade + Claude |
| 2026-10-15 | 2 | Installed Ubuntu Server 26.04.1. **Installer didn't offer the 120 GB free space on this MBR disk** (no free-space line, no *Add Partition*); made it from the installer shell with `parted -s /dev/sda unit s mkpart primary ext4 1213487104s 1465149167s` (sda4), went Back → Custom so the installer re-read the disk, then sda4 → ext4, `/`; boot device was picked automatically. Sections 1–3 untouched. No cable, and Wi-Fi wasn't saved by the installer: added `/etc/netplan/60-wifi.yaml` (wlp3s0, DHCP, chmod 600) by hand; ping works. Host name came out `cucumberstaging` (no hyphen): fix in Phase 4 | Jade + Claude |
| 2026-10-15 | 3 | Asus on Wi-Fi at **192.168.101.20** (router reservation still to do). `ssh-copy-id` with the Mac's `id_ed25519`; Mac `~/.ssh/config` has `Host cucumber-staging`. `ssh cucumber-staging` works without a password: Ubuntu 26.04.1 LTS, `/` = sda4 118 GB (105 GB free), 11 GiB RAM | Jade + Claude |
| 2026-10-16 | 3 | At the lab: added the lab Wi-Fi to `60-wifi.yaml` (home kept); Asus now **192.168.1.36**, Mac `~/.ssh/config` updated | Jade + Claude |
| 2026-10-16 | 4 | `deploy/setup-staging.sh` run. First run stopped at step 5 (`sshd -t` failed, likely no `/run/sshd` because SSH starts on demand); script now makes it and shows the error; second run finished. Host name `cucumber-staging`; Docker 29.9.1, Compose v5.6.0, uv 0.13.1; firewall allows SSH from 192.168.1.0/24 and 192.168.101.0/24; password login refused over SSH. Start-up menu found waiting forever after an unclean stop: `GRUB_RECORDFAIL_TIMEOUT=5` fixes it. Deploy key added (read-only); clone, folders and `secrets.env` (chmod 600) made on the Asus. Restart test: came back alone with Docker running. **To do:** Windows not seen in the start-up menu (check `os-prober`); save the secrets in the password manager; router reservation | Jade + Claude |
| 2026-10-16 | 5 | First deploy of `main` (`e186610`): `Done: staging now runs main-e186610a753c`. A second deploy refused `scripts/__pycache__/` (written by running the deploy itself); fixed in PR #20 (`141c7f9`). `/health/` ok and the banner shown, through an SSH tunnel | Claude |
| 2026-10-16 | 6 | U0.4a G5 checks all passed ([G5 note](../roadmap/units/u0.4a-g5-verify.md)): deploy and second deploy, rollback of a broken build, production refusals, flags, banner, restore (15 s), release rehearsal with draft tags `2026.10.1`/`2026.10.2`, walk-throughs 65/65 and 42/42. Added `~/cucumber/tools` (scripts run from there now). Staging runs `2026.10.1`. **To do:** Owner sign-off; still open from Phase 4: Windows in the start-up menu, router reservation, secrets in the password manager | Claude |
| 2026-10-17 | 5 | U0.4b step 3 (container hardening, PR #30) deployed: `main-0c3c1f73dd03`, 1 min 37 s. Checked on the running containers: app read-only, user 10001, all capabilities dropped, 512 MB cap; database on the internal `backend` network plus `db-port`; `/health/` ok. Left over: an empty `cucumber-staging_default` network from before the split (harmless; remove with `docker network rm` when convenient) | Claude |
| 2026-10-17 | 7 | Tunnel `cucumber-staging` (`9265130d…`) in compose, 4 connections (Bangkok, Singapore); route `cucumber-staging.…` → `http://app:8000`. A first tunnel made by mistake (named *Cloudflared*, `ee00fe18…`) deleted. Tunnel `cucumber-staging-admin` (`81f13387…`) as systemd service `cucumber-admin-tunnel`, enabled, 4 connections; route `cucumber-staging-ssh.…` → `ssh://localhost:22`. `cloudflared` 2026.10.1 from Cloudflare's apt source; Docker and Cloudflare sources in automatic updates (`53cucumber-origins`). Mac: `cloudflared` from Homebrew, `cucumber-staging-remote` in `~/.ssh/config`; first login through the browser, then `hostname` → `cucumber-staging`, from `127.0.0.1`. Phone test passed (Access runbook). HSTS raised to 604800, same version deployed again, header checked. Tokens and the updated `secrets.env` in Bitwarden. **To do:** AC24 restart test; AC21 port check; AC22 again with the Mac on phone data | Jade + Claude |
