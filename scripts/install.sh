#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run this installer with sudo: sudo ./scripts/install.sh" >&2
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/malina-matrix}"
APP_USER="${SUDO_USER:-${USER}}"

if [[ -z "${APP_USER}" || "${APP_USER}" == "root" ]]; then
    echo "Run this installer through sudo from your normal Linux user account." >&2
    exit 1
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
    echo "Linux user '${APP_USER}' does not exist." >&2
    exit 1
fi

APP_GROUP="$(id -gn "${APP_USER}")"
SUPPLEMENTARY_GROUPS="spi i2c"

echo "[install] Installing operating-system prerequisites..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-dev build-essential rsync i2c-tools

for group in spi i2c; do
    if ! getent group "$group" >/dev/null; then
        groupadd "$group"
    fi
done

usermod -aG spi,i2c "$APP_USER"

echo "[install] Preparing application directory: ${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0755 "${APP_DIR}"
rsync -a \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='zegar.conf' \
    --exclude='data/' \
    --exclude='web/data.json' \
    "${SOURCE_DIR}/" "${APP_DIR}/"

install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0755 "${APP_DIR}/data" "${APP_DIR}/web"
if [[ ! -f "${APP_DIR}/zegar.conf" ]]; then
    install -o "${APP_USER}" -g "${APP_GROUP}" -m 0644 "${APP_DIR}/zegar.conf.example" "${APP_DIR}/zegar.conf"
    echo "[install] Created local configuration from zegar.conf.example."
else
    echo "[install] Existing zegar.conf preserved."
fi

echo "[install] Creating Python virtual environment..."
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
    python3 -m venv --system-site-packages "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 0755 "${APP_DIR}/scripts/install.sh" "${APP_DIR}/scripts/check.sh"

echo "[install] Installing systemd service..."
sed \
    -e "s|@APP_DIR@|${APP_DIR}|g" \
    -e "s|@SERVICE_USER@|${APP_USER}|g" \
    -e "s|@SERVICE_GROUP@|${APP_GROUP}|g" \
    -e "s|@SUPPLEMENTARY_GROUPS@|${SUPPLEMENTARY_GROUPS}|g" \
    "${APP_DIR}/systemd/malina-matrix.service" \
    > /etc/systemd/system/malina-matrix.service
chmod 0644 /etc/systemd/system/malina-matrix.service

systemctl daemon-reload
systemctl enable --now malina-matrix.service

echo
echo "[install] Malina Matrix has been installed."
echo "Service: sudo systemctl status malina-matrix"
echo "Logs:    sudo journalctl -u malina-matrix -f"
echo "Config:  ${APP_DIR}/zegar.conf"
echo "Web UI:  serve ${APP_DIR}/web with Nginx (see nginx/malina-matrix.conf)."
echo
echo "If this user was just added to the spi/i2c groups, log out and back in for interactive shell access."
