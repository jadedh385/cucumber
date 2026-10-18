#!/usr/bin/env bash
# The MacBook admin tunnel: SSH from anywhere through
# cucumber-ssh.southeastcanopy.com (U0.4b design §6.1, §8, AC22).
# Runbook: docs/runbooks/macbook-server-setup.md, Phase 4. Run once, from the Mac:
#   ssh cucumber-server 'zsh -lc "brew install cloudflared"'
#   scp deploy/setup-production-admin-tunnel.sh cucumber-server:
#   ssh -t cucumber-server sudo bash setup-production-admin-tunnel.sh
# It asks for the tunnel token (paste it; nothing shows). Safe to run again:
# every step overwrites its own file; Enter on an empty token keeps the old one.
#
# Not `cloudflared service install <token>`: that writes the token into a
# launchd file anyone on the Mac can read and shows it in `ps`. Here the token
# lives in a file only the service's user can read, and the service runs as
# `nobody`, starting at boot (before anyone logs in, AC24), outside Docker.
set -euo pipefail

LABEL="com.southeastcanopy.cucumber-admin-tunnel"
PLIST="/Library/LaunchDaemons/$LABEL.plist"
CLOUDFLARED="/opt/homebrew/bin/cloudflared"   # Homebrew's; `brew upgrade` keeps it current
TOKEN_DIR="/etc/cloudflared"
TOKEN_FILE="$TOKEN_DIR/admin-tunnel.token"
LOG_FILE="/var/log/cucumber-admin-tunnel.log"
RUN_AS="nobody"

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }

[[ $(uname) == Darwin ]] || fail "this is for the MacBook (macOS)"
[[ $EUID -eq 0 ]] || fail "run with sudo"

step "1. cloudflared from Homebrew"
[[ -x $CLOUDFLARED ]] || fail "no $CLOUDFLARED: as the admin (not sudo) run: brew install cloudflared"
"$CLOUDFLARED" --version

step "2. Tunnel token (only '$RUN_AS' can read it)"
install -d -m 0755 -o root -g wheel "$TOKEN_DIR"
read -rsp "Paste the cucumber-admin token, then Enter (blank keeps the old one): " token
echo
if [[ -n $token ]]; then
  [[ $token =~ ^[A-Za-z0-9+/=_-]{100,}$ ]] || fail "that doesn't look like a tunnel token; nothing saved"
  umask 077
  printf '%s\n' "$token" > "$TOKEN_FILE"
fi
unset token
[[ -s $TOKEN_FILE ]] || fail "no token saved yet; run again and paste it"
chown "$RUN_AS" "$TOKEN_FILE"
chmod 400 "$TOKEN_FILE"

step "3. Service $LABEL: starts at boot, outside Docker"
touch "$LOG_FILE" && chown "$RUN_AS" "$LOG_FILE" && chmod 644 "$LOG_FILE"   # no secrets in it; the admin can read it
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$CLOUDFLARED</string>
    <string>--no-autoupdate</string>
    <string>tunnel</string>
    <string>run</string>
    <string>--token-file</string>
    <string>$TOKEN_FILE</string>
  </array>
  <key>UserName</key><string>$RUN_AS</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_FILE</string>
  <key>StandardErrorPath</key><string>$LOG_FILE</string>
</dict>
</plist>
EOF
chown root:wheel "$PLIST"
chmod 644 "$PLIST"
plutil -lint "$PLIST" >/dev/null || fail "$PLIST isn't a valid plist"
launchctl bootout "system/$LABEL" 2>/dev/null || true
launchctl bootstrap system "$PLIST"
launchctl enable "system/$LABEL"

step "Check"
echo "token file: $(stat -f '%Lp %Su' "$TOKEN_FILE")"
sleep 8
echo "service:    $(launchctl print "system/$LABEL" | awk '$1=="state" {print $3; exit}')"
grep -E "Registered tunnel connection|ERR" "$LOG_FILE" | tail -4 || true
echo
echo "Done. The dashboard should show cucumber-admin as Healthy."
