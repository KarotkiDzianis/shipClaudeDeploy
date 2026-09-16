#!/usr/bin/env bash
# platform/ship/deploy/setup_approval_daemon.sh — installs the ONE
# persistent Telegram approval daemon (telegram/approval_bot/daemon.py)
# on this VM, as its own systemd service. Serves ALL Ship projects on
# this VM (one bot, one chat -- see telegram/approval_bot/bot.py's own
# docstring), not just one project -- run this ONCE per VM, not per
# project.
#
# BEFORE running this, create /etc/ship/telegram.env yourself (never via
# Claude, never in git) with exactly these four lines:
#
#   SHIP_CLAUDE_DEPLOY_BOT=<the real bot token from ~/claude/.env>
#   TELEGRAM_CHAT_ID_DZIANIS=<the real chat id from ~/claude/.env>
#   SHIP_ALLOWED_APPROVER_IDS=<your numeric Telegram user id, comma-separated if more than one>
#   SHIP_RELEASE_ROOT=/srv/apps
#
# Your numeric Telegram user id (NOT the bot token, NOT the chat id) is
# needed because the approval state machine allow-lists WHO may tap
# approve/block (§24) -- get it by messaging the bot once, then checking
# https://api.telegram.org/bot<TOKEN>/getUpdates in a browser and reading
# the "from":{"id": ...} field of your own message. Do this from your own
# machine, never paste the token into a shared chat.
#
# Usage (as a user with sudo, e.g. karotki_dzianis):
#   sudo bash setup_approval_daemon.sh
set -euo pipefail

RUNNER_USER="karotki_dzianis"
INSTALL_DIR="/opt/ship-platform"
ENV_FILE="/etc/ship/telegram.env"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo (it writes /etc/systemd/system and installs a systemd service)." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE -- create it first (see this script's own header comment for the exact format)." >&2
  exit 1
fi

echo "== 1/3: platform/ship checkout =="
if [ -d "$INSTALL_DIR/.git" ]; then
  sudo -u "${RUNNER_USER}" git -C "$INSTALL_DIR" pull --ff-only
else
  sudo -u "${RUNNER_USER}" git clone https://github.com/KarotkiDzianis/shipClaudeDeploy.git "$INSTALL_DIR"
fi

echo "== 2/3: Python deps =="
sudo -u "${RUNNER_USER}" pip3 install --user --break-system-packages -r "$INSTALL_DIR/requirements.txt"

echo "== 3/3: systemd service =="
cat > /etc/systemd/system/ship-approval-bot.service <<EOF
[Unit]
Description=Ship Telegram Approval Daemon (serves all Ship projects on this VM)
After=network.target

[Service]
Type=simple
User=${RUNNER_USER}
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/telegram/approval_bot/daemon.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ship-approval-bot.service

echo ""
echo "Done. Daemon status:"
systemctl status ship-approval-bot.service --no-pager -l
