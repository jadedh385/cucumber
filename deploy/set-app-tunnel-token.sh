#!/usr/bin/env bash
# Puts the cucumber-production tunnel token into production's secrets.env
# (runbook: docs/runbooks/macbook-server-setup.md, Phase 4). From this Mac:
#   scp deploy/set-app-tunnel-token.sh cucumber-server:
#   ssh -t cucumber-server bash set-app-tunnel-token.sh
# A bash script because the production Mac's shell is zsh, where `read -p`
# does not show a prompt (a zsh one-liner once saved an empty token).
set -euo pipefail
read -rsp "Paste the cucumber-production token, then Enter: " t; echo
[[ $t =~ ^[A-Za-z0-9+/=_-]{100,}$ ]] || { echo "That doesn't look like a tunnel token; nothing saved."; exit 1; }
cd ~/cucumber/production
sed -i "" "s|^TUNNEL_TOKEN=.*|TUNNEL_TOKEN=$t|; s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES=tunnel|" secrets.env
echo "Saved (token length ${#t})."
