#!/usr/bin/env bash
# One-time set-up of the Asus staging server (runbook: docs/runbooks/
# asus-staging-setup.md, Phase 4, steps 1-9). Run once, from the Mac:
#   ssh -t cucumber-staging sudo bash setup-staging.sh
# Safe to run again: every step checks or overwrites its own file.
set -euo pipefail

ADMIN_USER="staging-admin"
HOST_NAME="cucumber-staging"
TIME_ZONE="Asia/Bangkok"
# Networks allowed to reach SSH: the lab and home Wi-Fi.
SSH_NETWORKS=("192.168.1.0/24" "192.168.101.0/24")
REBOOT_TIME="04:00"
MENU_SECONDS=5

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "run with sudo"
[[ -s /home/$ADMIN_USER/.ssh/authorized_keys ]] \
  || fail "no SSH key for $ADMIN_USER yet (Phase 3); password login must stay on"

step "0. Host name -> $HOST_NAME"
hostnamectl set-hostname "$HOST_NAME"
sed -i "s/^127\.0\.1\.1.*/127.0.1.1 $HOST_NAME/" /etc/hosts
# Stop cloud-init putting the installer's name back at start-up.
echo "preserve_hostname: true" > /etc/cloud/cloud.cfg.d/99-cucumber.cfg

step "1. Ubuntu updates; automatic security updates, restart at $REBOOT_TIME"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q
apt-get install -y -q unattended-upgrades ca-certificates curl git
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52cucumber-reboot <<EOF
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "$REBOOT_TIME";
EOF

step "2. Time zone $TIME_ZONE"
timedatectl set-timezone "$TIME_ZONE"

step "3. Lid closed = keep running; no sleep or hibernate"
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/90-cucumber-lid.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
systemctl mask --quiet sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl kill -s HUP systemd-logind

step "4. Firewall: SSH only, only from ${SSH_NETWORKS[*]}"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
for network in "${SSH_NETWORKS[@]}"; do
  ufw allow from "$network" to any port 22 proto tcp
done
ufw --force enable

step "5. SSH: keys only"
cat > /etc/ssh/sshd_config.d/10-cucumber-keys-only.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
# Ubuntu starts SSH on demand, so the folder `sshd -t` needs may not exist yet.
mkdir -p /run/sshd
if ! check_output=$(sshd -t 2>&1); then
  fail "SSH settings check failed; nothing reloaded: $check_output"
fi
systemctl try-reload-or-restart ssh

step "6. Docker Engine + Compose (Docker's own source)"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $VERSION_CODENAME
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker "$ADMIN_USER"

step "7. uv for $ADMIN_USER"
sudo -u "$ADMIN_USER" -H sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

step "8. Start-up menu: Ubuntu first, Windows listed, $MENU_SECONDS-second wait"
cat > /etc/default/grub.d/90-cucumber.cfg <<EOF
GRUB_DEFAULT=0
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=$MENU_SECONDS
# After a power cut, still start Ubuntu by itself instead of waiting forever.
GRUB_RECORDFAIL_TIMEOUT=$MENU_SECONDS
GRUB_DISABLE_OS_PROBER=false
EOF
update-grub

step "Check"
echo "host name:  $(hostname)"
echo "time:       $(date)"
echo "docker:     $(docker --version)"
echo "compose:    $(docker compose version)"
echo "uv:         $(sudo -u "$ADMIN_USER" -H /home/$ADMIN_USER/.local/bin/uv --version)"
echo "menu:       $(grep -E '^menuentry' /boot/grub/grub.cfg | cut -d"'" -f2 | paste -sd '|' -)"
ufw status | sed 's/^/firewall:   /'
echo
echo "Done. Step 9 (Windows clock) needs nothing now: if Windows ever shows the"
echo "wrong time, Settings -> Time -> Sync now."
