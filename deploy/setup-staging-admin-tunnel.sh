#!/usr/bin/env bash
# The Asus admin tunnel: SSH from anywhere through
# cucumber-staging-ssh.southeastcanopy.com (U0.4b design §6.1, §8, Q1).
# Runbook: docs/runbooks/asus-staging-setup.md, Phase 7. Run once, from the Mac:
#   scp deploy/setup-staging-admin-tunnel.sh cucumber-staging:
#   ssh -t cucumber-staging sudo bash setup-staging-admin-tunnel.sh
# It asks for the tunnel token (paste it; nothing shows). Safe to run again:
# every step overwrites its own file; Enter on an empty token keeps the old one.
#
# Not `cloudflared service install <token>`: that writes the token into a
# unit file anyone can read and shows it in `ps`. Here the token lives in a
# root-only file and the service runs as a throwaway user with no powers.
set -euo pipefail

SERVICE="cucumber-admin-tunnel"
TOKEN_FILE="/etc/cloudflared/admin-tunnel.env"
KEYRING="/usr/share/keyrings/cloudflare-public-v2.gpg"

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "run with sudo"

step "1. cloudflared from Cloudflare's own source (suite 'any')"
export DEBIAN_FRONTEND=noninteractive
install -m 0755 -d /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg -o "$KEYRING"
chmod a+r "$KEYRING"
cat > /etc/apt/sources.list.d/cloudflared.sources <<EOF
Types: deb
URIs: https://pkg.cloudflare.com/cloudflared
Suites: any
Components: main
Signed-By: $KEYRING
EOF
apt-get update -q
apt-get install -y -q cloudflared

step "2. Automatic updates also cover Docker's and Cloudflare's sources"
# Ubuntu's automatic updates only take Ubuntu's own sources unless told.
cat > /etc/apt/apt.conf.d/53cucumber-origins <<'EOF'
Unattended-Upgrade::Origins-Pattern {
  "origin=Docker,label=Docker CE";
  "origin=cloudflared,label=cloudflared";
};
EOF

step "3. Tunnel token (root-only file)"
install -d -m 0700 /etc/cloudflared
read -rsp "Paste the cucumber-staging-admin token, then Enter (blank keeps the old one): " token
echo
if [[ -n $token ]]; then
  [[ $token =~ ^[A-Za-z0-9+/=_-]{100,}$ ]] || fail "that doesn't look like a tunnel token; nothing saved"
  umask 077
  printf 'TUNNEL_TOKEN=%s\n' "$token" > "$TOKEN_FILE"
fi
unset token
[[ -s $TOKEN_FILE ]] || fail "no token saved yet; run again and paste it"
chmod 600 "$TOKEN_FILE"

step "4. Service $SERVICE: starts at boot, outside Docker"
cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=Cloudflare tunnel for SSH (cucumber-staging-ssh)
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=$TOKEN_FILE
ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run
Restart=always
RestartSec=5
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"

step "Check"
echo "cloudflared: $(cloudflared --version)"
echo "token file:  $(stat -c '%a %U' "$TOKEN_FILE")"
sleep 5
echo "service:     $(systemctl is-active "$SERVICE")"
journalctl -u "$SERVICE" -n 20 --no-pager -o cat | grep -E "Registered tunnel connection|ERR" | tail -4 || true
echo
echo "Done. The dashboard should show cucumber-staging-admin as Healthy."
