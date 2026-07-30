#!/bin/sh
set -eu

DEPLOY_USER="${DEPLOY_USER:-nc-user}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/restaurant-pos}"
TIMEZONE="${TIMEZONE:-Asia/Bangkok}"

run() {
  printf '\n$ %s\n' "$*"
  "$@"
}

run_sh() {
  printf '\n$ %s\n' "$*"
  sh -c "$*"
}

confirm() {
  prompt="$1"
  printf '%s [yes/NO]: ' "$prompt"
  read answer
  if [ "$answer" != "yes" ]; then
    printf 'Cancelled.\n' >&2
    exit 1
  fi
}

printf 'Restaurant POS v0.1 VPS bootstrap starting...\n'
printf 'Deploy user: %s\n' "$DEPLOY_USER"
printf 'Deploy dir: %s\n' "$DEPLOY_DIR"
printf 'Timezone: %s\n' "$TIMEZONE"

printf '\n== 1. Verify OS ==\n'
run cat /etc/os-release
run uname -a

printf '\n== 2. Verify CPU/RAM/Disk ==\n'
run nproc
run lscpu
run free -h
run df -h

printf '\n== 3. Update Ubuntu package index ==\n'
run sudo apt update

printf '\n== 4. Upgrade Ubuntu packages ==\n'
confirm "Run sudo apt upgrade -y now?"
run sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y

printf '\n== 5. Set timezone ==\n'
run sudo timedatectl set-timezone "$TIMEZONE"
run timedatectl

printf '\n== 6. Install base packages ==\n'
run sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  git \
  curl \
  ca-certificates \
  ufw \
  fail2ban

printf '\n== 7. Install Docker Engine repository ==\n'
run sudo install -m 0755 -d /etc/apt/keyrings
run_sh "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null"
run sudo chmod a+r /etc/apt/keyrings/docker.asc
run_sh "printf '%s\n' \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \$(. /etc/os-release && printf '%s' \"\$VERSION_CODENAME\") stable\" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null"
run sudo apt update

printf '\n== 8. Install Docker Engine and Compose plugin ==\n'
run sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

printf '\n== 9. Enable Docker service ==\n'
run sudo systemctl enable --now docker
run sudo systemctl status docker --no-pager

printf '\n== 10. Add user to docker group ==\n'
run sudo usermod -aG docker "$DEPLOY_USER"
printf 'NOTE: docker group membership applies after the next login session.\n'

printf '\n== 11. Configure UFW ==\n'
run sudo ufw allow OpenSSH
run sudo ufw allow 80/tcp
run sudo ufw allow 443/tcp
confirm "Enable UFW firewall now? Confirm SSH access is allowed before continuing."
run sudo ufw --force enable

printf '\n== 12. Create deployment directory ==\n'
run sudo mkdir -p "$DEPLOY_DIR"
run sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_DIR"
run sudo chmod 755 "$DEPLOY_DIR"

printf '\n== 13. Final verification ==\n'
run docker --version
run docker compose version
run git --version
run sudo ufw status verbose
run timedatectl
run df -h
run free -h

printf '\nBootstrap complete. Log out and SSH back in so docker group membership takes effect.\n'
