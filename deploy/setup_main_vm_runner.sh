#!/usr/bin/env bash
# platform/ship/deploy/setup_main_vm_runner.sh — ONE script that sets up
# everything ship-sandbox needs on the VM (§Rule 10: Claude never SSHes
# or runs this itself -- Dzianis runs exactly this, once, on the VM).
#
# What it does, in order:
#   1. Creates /srv/apps (Ship's release_root) owned by RUNNER_USER, no
#      sudo needed for install/switch/rollback file operations.
#   2. Installs a sudoers drop-in that grants RUNNER_USER passwordless
#      sudo for EXACTLY ONE command: `systemctl restart ship-sandbox`.
#      Nothing else -- no blanket sudo, no other service, never reboot.
#   3. Installs deploy/ship-sandbox.service into /etc/systemd/system/ and
#      reloads systemd (does not start it -- there's no release to run
#      yet; the first real deploy's restart_fn starts it for the first
#      time).
#   4. Downloads and configures a GitHub Actions self-hosted runner,
#      scoped to the ship-sandbox repo only, labeled exactly
#      [self-hosted, linux, ship-prod] (matches registry/targets.yml),
#      and installs it as its own systemd service so it survives reboots.
#
# You need a registration token first (expires in ~1 hour, single use):
#   https://github.com/KarotkiDzianis/ship-sandbox/settings/actions/runners/new
#   -> copy the token shown in the "./config.sh ... --token <TOKEN>" line
#
# Usage (as a user with sudo, e.g. karotki_dzianis):
#   sudo bash setup_main_vm_runner.sh <REGISTRATION_TOKEN>
#
# Known limitation (documented, not fixed here): this registers the
# runner against the ship-sandbox REPO specifically -- a future project
# in its own separate repo (e.g. tradepulse) will need either its own
# runner registration or an org-level runner pool. Out of scope for this
# first sandbox test (see docs/SHIP_V0_ARCHITECTURE.md).
set -euo pipefail

TOKEN="${1:?Usage: sudo bash setup_main_vm_runner.sh <REGISTRATION_TOKEN>}"
RUNNER_USER="karotki_dzianis"
RUNNER_DIR="/home/${RUNNER_USER}/actions-runner-ship-sandbox"
REPO_URL="https://github.com/KarotkiDzianis/ship-sandbox"
RUNNER_VERSION="2.321.0"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo (it writes /etc/sudoers.d, /etc/systemd/system, and installs a systemd service)." >&2
  exit 1
fi

echo "== 1/4: release_root =="
mkdir -p /srv/apps
chown "${RUNNER_USER}:${RUNNER_USER}" /srv/apps

echo "== 2/4: sudoers (scoped to exactly one command) =="
SUDOERS_FILE=/etc/sudoers.d/ship-sandbox
echo "${RUNNER_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart ship-sandbox.service" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

echo "== 3/4: ship-sandbox.service unit =="
cp "$(dirname "$0")/ship-sandbox.service" /etc/systemd/system/ship-sandbox.service
systemctl daemon-reload

echo "== 4/4: GitHub Actions self-hosted runner =="
sudo -u "${RUNNER_USER}" mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
sudo -u "${RUNNER_USER}" curl -sL -o actions-runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
sudo -u "${RUNNER_USER}" tar xzf actions-runner.tar.gz
sudo -u "${RUNNER_USER}" ./config.sh --url "$REPO_URL" --token "$TOKEN" \
  --labels self-hosted,linux,ship-prod --name main-vm-ship-sandbox --unattended --replace

./svc.sh install "${RUNNER_USER}"
./svc.sh start

echo ""
echo "Done. Runner status:"
./svc.sh status
