#!/usr/bin/env bash
# One-time set-up of production on the MacBook (runbook: docs/runbooks/
# macbook-server-setup.md, Phase 3). Phases 1-2 already did the system set-up
# (sleep, firewall, SSH, Docker Desktop, uv); this only checks it. No sudo.
# Run from the Mac, as the MacBook's admin:
#   scp deploy/setup-production.sh cucumber-server:
#   ssh cucumber-server bash setup-production.sh
# Safe to run again: each step skips what is already there, and the secrets
# file is never made twice.
set -euo pipefail

REPO="jadedh385/cucumber"
GITHUB_ALIAS="github-cucumber"   # this deploy key only; the admin's own GitHub access is untouched
DEPLOY_KEY="$HOME/.ssh/cucumber_deploy_ed25519"
HOME_DIR="$HOME/cucumber"
PRODUCTION="$HOME_DIR/production"
TOOLS="$HOME_DIR/tools"
APP_PORT=8000
DB_LOCAL_PORT=5436
# Homebrew and Docker Desktop's tools; an SSH command gets no login PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'STOPPED: %s\n' "$*" >&2; exit 1; }
port_owner() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1" (pid "$2")"}'; }

[[ $(uname) == Darwin ]] || fail "this is for the MacBook (macOS)"
[[ $EUID -ne 0 ]] || fail "run as the admin account, not with sudo"

step "1. Tools: git, uv, Docker Desktop running"
command -v git >/dev/null || fail "no git: brew install git"
command -v uv >/dev/null || fail "no uv: brew install uv"
docker info >/dev/null 2>&1 || fail "Docker Desktop isn't running: open it, wait for it to start, run again"
# Over SSH, Docker Desktop's keychain helper can fail even for public images.
docker pull -q busybox:1.37 >/dev/null 2>&1 \
  || fail "docker can't pull images over SSH (keychain?). See the runbook, Phase 3, 'If docker can't pull'"
docker rmi -f busybox:1.37 >/dev/null 2>&1 || true

step "2. Ports $APP_PORT and $DB_LOCAL_PORT free for production"
for port in "$APP_PORT" "$DB_LOCAL_PORT"; do
  owner=$(port_owner "$port")
  if [[ -n $owner ]] && ! docker compose -p cucumber-production ps -q 2>/dev/null | grep -q .; then
    fail "port $port is taken by $owner (the old spike's dev server?). Stop it, then run again"
  fi
done

step "3. GitHub read-only deploy key"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[[ -f $DEPLOY_KEY ]] || ssh-keygen -q -t ed25519 -N "" -C "cucumber-server production deploy key" -f "$DEPLOY_KEY"
touch "$HOME/.ssh/config" && chmod 600 "$HOME/.ssh/config"
if ! grep -q "^Host $GITHUB_ALIAS\$" "$HOME/.ssh/config"; then
  cat >> "$HOME/.ssh/config" <<EOF

Host $GITHUB_ALIAS
    HostName github.com
    User git
    IdentityFile $DEPLOY_KEY
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
EOF
fi
REMOTE="git@$GITHUB_ALIAS:$REPO.git"
if ! git ls-remote "$REMOTE" HEAD >/dev/null 2>&1; then
  echo "GitHub doesn't know this key yet. Add it at GitHub -> $REPO -> Settings ->"
  echo "Deploy keys -> Add deploy key, title 'cucumber-server production',"
  echo "'Allow write access' UNticked:"
  echo
  cat "$DEPLOY_KEY.pub"
  echo
  echo "Then run this script again."
  exit 2
fi

step "4. Folders (only this account can open them)"
for folder in "$HOME_DIR" "$PRODUCTION" "$PRODUCTION/backups" "$PRODUCTION/logs"; do
  mkdir -p "$folder" && chmod 700 "$folder"
done

step "5. Clones: tools on main, production/src for the deploy command"
for clone in "$TOOLS" "$PRODUCTION/src"; do
  if [[ -d $clone/.git ]]; then
    echo "$clone already there"
  else
    git clone -q "$REMOTE" "$clone"
  fi
done
git -C "$TOOLS" checkout -q main && git -C "$TOOLS" pull -q --ff-only

step "6. Secrets file (made here; values never shown)"
if [[ -f $PRODUCTION/secrets.env ]]; then
  [[ $(stat -f %Lp "$PRODUCTION/secrets.env") == 600 ]] || fail "$PRODUCTION/secrets.env must be chmod 600"
  echo "$PRODUCTION/secrets.env already there: kept as it is"
else
  (cd "$TOOLS" && uv run -q --no-dev python -m scripts.make_secrets production)
fi

step "Check (for the setup log)"
echo "macOS:      $(sw_vers -productVersion)"
echo "docker:     $(docker --version)"
echo "compose:    $(docker compose version --short)"
echo "uv:         $(uv --version)"
echo "Docker mem: $(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 )) MiB"
echo "disk free:  $(df -h "$HOME" | awk 'NR==2 {print $4}')"
echo "sleep (AC): $(pmset -g custom | awk '/AC Power/ {ac=1} ac && $1=="sleep" {print $2; exit}') (want 0)"
echo "firewall:   $(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null | sed 's/^Firewall is //')"
echo "FileVault:  $(fdesetup status | head -1)"
echo
echo "Done. Next: save secrets.env in Bitwarden, then the first production deploy (runbook Phase 3)."
