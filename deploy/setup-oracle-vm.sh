#!/usr/bin/env bash
# Run ONCE on a fresh Oracle Cloud "Always Free" Ubuntu VM (as the ubuntu user,
# with sudo). Installs Docker, opens the two firewall layers Oracle VMs have
# (OS-level iptables AND the cloud Security List — this script only handles
# the OS side; the Security List must be opened in the OCI console, see
# DEPLOY_ORACLE.md), and clones this repo.
#
# Usage:
#   scp -r deploy ubuntu@<VM_IP>:~/
#   ssh ubuntu@<VM_IP>
#   bash deploy/setup-oracle-vm.sh
set -euo pipefail

REPO_URL="${REPO_URL:-}"
APP_DIR="$HOME/TGL"

echo "== 1/5 Installing Docker =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "   Docker installed. You'll need to log out and back in for the group"
  echo "   change to apply (or run the rest of this script with 'sudo')."
fi

echo "== 2/5 Opening OS-level firewall (iptables) for HTTP/HTTPS =="
# Oracle's stock Ubuntu image ships with iptables rules that DROP everything
# except SSH by default. Docker manages its own chains for published ports,
# but Caddy's 80/443 publish still needs these host-level ACCEPT rules.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4 >/dev/null || true

echo "== 3/5 Cloning the repo =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
elif [ -n "$REPO_URL" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "   REPO_URL not set and $APP_DIR doesn't exist yet."
  echo "   Either: REPO_URL=https://github.com/you/TGL.git bash deploy/setup-oracle-vm.sh"
  echo "   or copy the repo to $APP_DIR yourself, then re-run this script."
  exit 1
fi

echo "== 4/5 Environment file =="
cd "$APP_DIR"
if [ ! -f backend/.env ]; then
  cp backend/.env.production.example backend/.env
  echo "   Created backend/.env from the template — EDIT IT NOW:"
  echo "     - SECRET_KEY   (python3 -c \"import secrets; print(secrets.token_urlsafe(48))\")"
  echo "     - PUBLIC_ORIGIN"
fi
if [ ! -f .env ]; then
  read -rp "   Domain that points at this VM's public IP (e.g. tgl-admin.duckdns.org): " DOMAIN_INPUT
  echo "DOMAIN=$DOMAIN_INPUT" > .env
fi

echo "== 5/5 Done. Next steps =="
echo "   1. nano backend/.env      # fill in SECRET_KEY and PUBLIC_ORIGIN"
echo "   2. docker compose up -d --build"
echo "   3. docker compose exec api python create_admin.py"
