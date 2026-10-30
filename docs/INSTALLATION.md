# Installation and deployment

This guide documents the repository installer and the manual deployment pieces. The tested target is Raspberry Pi OS / Debian with Python 3.10 or newer and a MAX7219 display connected over SPI.

## Before installing

1. Connect the matrix chain and optional sensor.
2. Enable SPI, and enable I²C / 1-Wire when required.
3. Confirm the display power supply and common ground.
4. Make sure the Linux account that will run the service exists.

## Automated installation

Clone the repository and run the installer as your regular user through sudo:

```bash
git clone https://github.com/mciochu/MalinaMatrix.git
cd MalinaMatrix
sudo ./scripts/install.sh
```

The installer:

- installs Python, development headers, virtual-environment support, rsync and I²C tools;
- creates SPI and I²C groups if they do not exist and adds the service user;
- copies the project to `/opt/malina-matrix` (override with `APP_DIR=/your/path`);
- preserves an existing `zegar.conf` and creates it from the example only on first install;
- creates a Python virtual environment and installs `requirements.txt`;
- renders the systemd unit with the selected paths and user;
- enables and starts `malina-matrix.service`.

The script does not install Nginx. Install it separately when you want the browser dashboard served over HTTP.

## Configuration

The installer copies `zegar.conf.example` to the application directory as `zegar.conf` only if a local config does not already exist. Edit the resulting file:

```bash
sudo -u "$USER" nano /opt/malina-matrix/zegar.conf
```

Set the physical panel count and orientation under `[hardware]`. Set your actual coordinates under `[weather]` if you want a local forecast. The default sample uses neutral coordinates and should be customized.

The database and JSON export paths are project-relative by default:

- `data/sensor_data.db`
- `web/data.json`

The systemd unit sets `ZEGAR_CONFIG_PATH` explicitly and starts the application from the project directory.

## Check service status and logs

```bash
sudo systemctl status malina-matrix
sudo journalctl -u malina-matrix -n 100 --no-pager
sudo journalctl -u malina-matrix -f
```

Restart after hardware, sensor backend, module, plugin list or web listener changes:

```bash
sudo systemctl restart malina-matrix
```

## Browser dashboard with Nginx

Install Nginx:

```bash
sudo apt install -y nginx
```

The repository includes `nginx/malina-matrix.conf`. It expects the standard installation path:

```bash
sudo cp nginx/malina-matrix.conf /etc/nginx/sites-available/malina-matrix
sudo ln -s /etc/nginx/sites-available/malina-matrix /etc/nginx/sites-enabled/malina-matrix
sudo nginx -t
sudo systemctl reload nginx
```

Open the Raspberry Pi address from a device on the same network. The page loads Chart.js from a public CDN and reads measurements from the locally generated `data.json`.

The application HTTP API defaults to port 8088 and is contacted directly by the browser. It has no built-in authentication. Keep it on a trusted LAN and do not expose it to the public Internet. Restrict access with a firewall or put an authenticated reverse proxy in front of it if remote access is required.

## Manual / development run

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp zegar.conf.example zegar.conf
```

Stop the systemd service before running a foreground copy. Two processes must not try to use the same SPI display:

```bash
sudo systemctl stop malina-matrix
.venv/bin/python zegar.py --verbose
```

Use Ctrl+C to stop it. Then restart the service if required.

## Updating the project

Back up the local configuration and runtime data before updating. Fetch the current repository version, then run the checks:

```bash
git pull --ff-only
./scripts/check.sh
sudo systemctl restart malina-matrix
```

The repository installer intentionally preserves an existing local config; updates should not overwrite your sensor history database or generated JSON.
