#!/usr/bin/env bash
# platform/ship/deploy/setup_approval_daemon.sh — installs the ONE
# persistent Telegram approval daemon (telegram/approval_bot/daemon.py)
# on this VM, as its own systemd service. Serves ALL Ship projects on
# this VM (one bot, one chat -- see telegram/approval_bot/bot.py's own
# docstring), not just one project -- run this ONCE per VM, not per
# project.
#
# BEFORE running this, create /etc/ship/telegram.env yourself (never via
# Claude, never in git) with these four lines:
#
#   SHIP_CLAUDE_DEPLOY_BOT=<the real bot token from ~/claude/.env>
#   TELEGRAM_CHAT_ID_DZIANIS=<the real chat id from ~/claude/.env>
#   SHIP_ALLOWED_APPROVER_IDS=$TELEGRAM_CHAT_ID_DZIANIS
#   SHIP_RELEASE_ROOT=/srv/apps
#
# SHIP_ALLOWED_APPROVER_IDS restricts who may tap approve/block (§24) --
# written as a literal `$VAR` reference on purpose: for a private 1-on-1
# chat with the bot, Telegram's chat_id IS your own numeric user id
# (they're the same number), so there's no separate value to look up.
# This file is sourced by bash below (real $VAR expansion), NOT loaded
# via systemd's own EnvironmentFile= (that's a plain KEY=VALUE parser
# with no expansion at all -- it would keep the literal string
# "$TELEGRAM_CHAT_ID_DZIANIS", not resolve it). Only replace this line
# with actual comma-separated ids if more than one person should be able
# to approve, or if this bot's chat is ever not a private 1-on-1 chat.
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
mkdir -p "$INSTALL_DIR"
chown "${RUNNER_USER}:${RUNNER_USER}" "$INSTALL_DIR"
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
WorkingDirectory=${INSTALL_DIR}
ExecStart=/bin/bash -c 'set -a; source ${ENV_FILE}; exec /usr/bin/python3 ${INSTALL_DIR}/telegram/approval_bot/daemon.py'
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
