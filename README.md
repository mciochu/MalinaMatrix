# Malina Matrix

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)\n[![CI](https://github.com/mciochu/MalinaMatrix/actions/workflows/ci.yml/badge.svg)](https://github.com/mciochu/MalinaMatrix/actions/workflows/ci.yml)

**Malina Matrix** is a modular Raspberry Pi clock and sensor dashboard for chained MAX7219 LED matrices. It combines a readable LED clock with optional environmental readings, a compact history graph, weather information, a browser dashboard, and extension points for custom sensors, screens, and background modules.

The project is designed for Raspberry Pi Zero-class hardware. Slow sensor reads, network requests, history exports, and custom screen rendering are kept away from the main display loop. Optional features are controlled from one configuration file.

> The default configuration is conservative: the Bluetooth audio visualizer is disabled, animations are off, and the daytime clock uses the bundled MatrixChunky8X font.

## Hardware used in the reference build

This is the hardware that the maintainer's working clock is based on. Where an exact board or manufacturer part number was not recorded, the entry is deliberately described by its confirmed type rather than an invented model.

| Part | Model / specification | Role and status |
|---|---|---|
| Single-board computer | **Raspberry Pi Zero W** | Main computer running Raspberry Pi OS / Debian and the Python application. |
| LED display | **8 × MAX7219 8×8 LED matrix modules**, chained together | Main clock display; 64×8 pixels in the reference layout. The exact module brand/PCB revision is not specified. |
| Environmental sensor | **BME280** I²C sensor | Measures temperature, relative humidity and pressure. The exact breakout-board manufacturer/model is not recorded. |
| Display interface | SPI0 | Sends image data from the Raspberry Pi to the MAX7219 chain. |
| Sensor interface | I²C bus 1 | Reads the BME280. |
| Power | 5 V supply suitable for the Pi and LED chain | Exact power-supply model and current rating used in the reference build are not documented; size it for your own hardware. |

### Other software-supported hardware

These are supported by optional drivers, but are **not part of the confirmed reference build**:

- DS18B20 — 1-Wire temperature sensor.
- SHT31 — I²C temperature and humidity sensor.
- DHT22 — GPIO temperature and humidity sensor.

The lamp feature is a software mode that uses the existing MAX7219 matrix as a light surface; it does not imply a separate physical lamp module. Bluetooth audio visualizer code is present but disabled by default.

## Features

- **MAX7219 clock:** configurable panel chain, orientation, rotation, day/night layout, 12/24-hour format, and brightness.
- **Environmental readings:** BME280 temperature, humidity, and pressure, polled by a background sensor worker.
- **On-matrix graph:** compact history graph with a dedicated humidity bar-chart mode.
- **Weather:** daily forecast from [Open-Meteo](https://open-meteo.com/) using configurable coordinates; no API key is required.
- **Browser dashboard:** current readings, historical charts, display test controls, lamp controls, and text messages.
- **LED lamp mode:** turns the matrix into a pixel light using the MAX7219 hardware intensity setting; no per-pixel PWM is used.
- **Live configuration reload:** selected settings such as fonts, screen order, brightness, clock format, and screen timing apply without restarting the service.
- **Extension system:** add sensor backends, custom screens, and optional background modules as separate Python files.
- **Bundled assets:** Matrix BDF fonts and monochrome weather icons are part of the application.

## Hardware

The default setup targets:

- Raspberry Pi with Raspberry Pi OS or another Debian-based Linux distribution.
- Eight chained MAX7219 8×8 LED matrix modules (64×8 pixels total). The panel count is configurable.
- Optional BME280 sensor connected over I²C. Common addresses 0x76 and 0x77 are supported.
- SPI enabled for the MAX7219 chain.
- I²C enabled when a sensor is used.

Other MAX7219 chain sizes can be configured, but the built-in screen layout and sample custom-screen contract are designed for an 8-pixel-high display. The MAX7219 display path and BME280 readings have been verified on the maintainer's Raspberry Pi. DS18B20, SHT31 and DHT22 adapters are included, but require the matching hardware, wiring and optional libraries; validate each adapter on your own setup.

## Repository layout

~~~text
MalinaMatrix/
├── zegar.py                         # Application entry point
├── zegar.conf.example               # Portable example configuration
├── requirements.txt
├── requirements-optional.txt
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── README.md
├── CONTRIBUTING.md
├── zegar_app/
│   ├── config.py                    # Validated settings and safe live reload
│   ├── display.py                   # MAX7219 setup and rendering loop
│   ├── sensor_hub.py                # Background sensor polling and cache
│   ├── sensors.py                   # Existing BME280 implementations
│   ├── history.py                   # SQLite history and graph aggregation
│   ├── weather.py                   # Cached Open-Meteo forecast
│   ├── network.py                   # Non-blocking connectivity status
│   ├── web_control.py               # Local HTTP controls (port 8088 by default)
│   ├── fonts.py                     # BDF font loader and font discovery
│   ├── core/
│   │   ├── module_manager.py        # Lazy optional module lifecycle
│   │   ├── plugin_loader.py         # Explicit extension loading
│   │   ├── screen_registry.py       # Built-in and custom screen registry
│   │   └── bitmap_assets.py         # JSON / PBM monochrome image loader
│   ├── extensions/
│   │   ├── sensors/                 # BME280, DS18B20, SHT31, DHT22, template
│   │   ├── screens/                 # Example custom screen
│   │   └── modules/                 # Optional background-module template
│   └── assets/
│       ├── fonts/                   # Bundled 6-series and 8-series BDF fonts
│       ├── icons/                   # Built-in 8×8 weather icons
│       └── images/                  # Example user bitmap
├── web/
│   └── index.html                   # Browser dashboard
├── systemd/
│   └── malina-matrix.service
├── nginx/
│   └── malina-matrix.conf
├── scripts/
│   ├── install.sh
│   └── check.sh
└── tests/
    └── test_core.py
~~~

Runtime data is deliberately excluded from version control. The SQLite database lives under **data/** and the dashboard reads the generated **web/data.json** file.

## Quick start

### 1. Prepare the Raspberry Pi

Enable SPI and, when using a BME280, I²C. On Raspberry Pi OS:

~~~bash
sudo raspi-config
~~~

Open **Interface Options**, enable **SPI** and **I²C**, then reboot if requested.

Check that the SPI device is present:

~~~bash
ls -l /dev/spidev*
~~~

For a BME280, install I²C utilities and check the detected address:

~~~bash
sudo apt update
sudo apt install -y i2c-tools
i2cdetect -y 1
~~~

### 2. Clone the project

~~~bash
git clone https://github.com/mciochu/MalinaMatrix.git
cd MalinaMatrix
~~~

### 3. Configure the hardware

Create the local configuration:

~~~bash
cp zegar.conf.example zegar.conf
nano zegar.conf
~~~

At minimum, check these values:

~~~ini
[hardware]
panel_count = 8
block_orientation = -90
rotation = 0
i2c_address = 0x76
i2c_port = 1

[weather]
latitude = 0.0
longitude = 0.0
~~~

Set the panel count and orientation to match your matrix chain. Set weather coordinates to your location. The local configuration is excluded by .gitignore so that personal paths and coordinates are not accidentally committed.

### 4. Install and start the service

The installer prepares a virtual environment, installs Python requirements, creates writable data directories, installs the systemd service, and enables it for the current Linux user:

~~~bash
sudo ./scripts/install.sh
~~~

Check the service:

~~~bash
sudo systemctl status malina-matrix
sudo journalctl -u malina-matrix -f
~~~

The installer preserves an existing local configuration. If no local configuration exists, it copies zegar.conf.example.

### 5. Run manually (optional)

Stop the service first so that two processes do not compete for the same SPI display:

~~~bash
sudo systemctl stop malina-matrix
.venv/bin/python zegar.py --verbose
~~~

Use Ctrl+C to stop the foreground process, then start the service again:

~~~bash
sudo systemctl start malina-matrix
~~~

## Browser dashboard

The static dashboard is in **web/index.html**. It provides:

- live sensor readings and historical charts;
- manual day/night and sensor-screen test modes;
- weather icon/text selection;
- LED lamp controls;
- text messages sent to the matrix.

The dashboard expects a static web server to serve the **web/** directory and the application to expose its local HTTP control API on port **8088**.

### Nginx example

The repository includes **nginx/malina-matrix.conf**. For a standard installation under **/opt/malina-matrix**, enable it with:

~~~bash
sudo cp nginx/malina-matrix.conf /etc/nginx/sites-available/malina-matrix
sudo ln -s /etc/nginx/sites-available/malina-matrix /etc/nginx/sites-enabled/malina-matrix
sudo nginx -t
sudo systemctl reload nginx
~~~

Then open the Raspberry Pi address in a browser, for example **http://raspberrypi.local/**.

The page loads Chart.js from a public CDN. Historical readings are served locally from **web/data.json**.

> **Network security:** the HTTP control API is intended for a trusted local network and does not provide user authentication. Do not expose TCP port 8088 directly to the public internet. Use a firewall and keep the dashboard on a trusted LAN.

## Configuration

All user-adjustable settings live in **zegar.conf**. The example file is fully commented in English.

| Section | Purpose |
|---|---|
| [modules] | Enable or disable sensors, history, graph, weather, Wi-Fi indicator, web control, lamp, audio, and animations. |
| [hardware] | MAX7219 panel count, orientation, rotation, chain order, and I²C bus settings. |
| [clock] | 12/24-hour format and seconds display. |
| [fonts] | Separate BDF or built-in fonts for daytime clock, sensor values, night clock, and messages. |
| [display] | Screen order, screen duration, refresh intervals, and night schedule. |
| [brightness] | Day/night matrix intensity and default lamp controls. |
| [sensor], [sensors] | Sensor polling interval and enabled sensor backends. |
| [sensors.<name>] | Per-backend settings such as I²C address or GPIO pin. |
| [history] | SQLite location, web data directory, history interval, graph window, and startup export. |
| [weather] | Coordinates, cache policy, HTTP timeout, and icon/text presentation. |
| [network] | Internet probe host, port, timeout, and interval. |
| [web] | HTTP bind address, port, and message duration. |
| [screens] | Enabled custom screens and their refresh/staleness limits. |
| [extensions] | Explicitly enabled optional background extensions. |
| [effects] | Animation timing. |
| [assets] | User bitmap directory. |

### Live reload and restart boundaries

The main loop checks the configuration file approximately every two seconds. It compares file metadata and does not repeatedly parse an unchanged file.

These settings are applied live after a valid update:

- font selections;
- day/night intensity;
- screen order for already loaded screens;
- screen dwell and refresh intervals;
- clock format and seconds display;
- night-mode enablement and schedule;
- history logging interval;
- weather icon/text presentation.

Changes that alter initialized hardware, service listeners, or the set of loaded plugins require a service restart. This includes hardware settings, enabling/disabling modules, changing sensor backends, changing the web port, and adding/removing extensions.

Configuration parsing is defensive. Invalid booleans, numbers, non-finite values, and out-of-range values fall back to defaults and are logged. A malformed update is rejected; the previous valid configuration remains active.

## Adding extensions

Extensions are loaded only when their names are explicitly listed in **zegar.conf**. The loader does not scan arbitrary Python files or import every file in an extension directory.

### Add a sensor backend

Create **zegar_app/extensions/sensors/my_sensor.py**:

~~~python
class MySensor:
    def read(self):
        return {"temp": 21.5, "hum": 48}

    def close(self):
        pass


def create(settings):
    # Import optional hardware libraries here, not at module import time.
    return MySensor()
~~~

Enable it:

~~~ini
[sensors]
enabled = bme280, my_sensor
~~~

The required contract is **create(settings)** returning an object with **read()**. The method returns a dictionary containing any of **temp**, **hum**, and **press**. Values must be numeric and finite. An optional **close()** method can release resources.

Built-in examples are provided for:

- **bme280** — existing BME280 implementation;
- **ds18b20** — Linux 1-Wire temperature sensor;
- **sht31** — Adafruit CircuitPython SHT31;
- **dht22** — Adafruit CircuitPython DHT22.

Additional hardware libraries are optional and should only be installed for the selected sensor.

### Add a custom screen

Create a Python file in **zegar_app/extensions/screens/** and enable its filename without the .py suffix:

~~~ini
[screens]
plugins = example_status
~~~

A screen module provides:

~~~python
SCREEN_ID = "example_status"
REQUIRES = ("sensors",)


def render(context):
    # Return exactly eight integer row masks.
    rows = [0] * 8
    rows[7] = 0x3F
    return rows
~~~

Each row is a bit mask. Bit 0 is the leftmost pixel; bit 63 is the rightmost pixel. The current renderer accepts an 8-row bitmap for the default 64×8 matrix.

Custom screens run on a dedicated worker and return validated bitmap data to the display loop. The main loop does not wait for a custom renderer. A screen that raises an exception, returns an invalid frame, or exceeds its staleness limit is disabled and the clock remains available. Python threads cannot safely terminate arbitrary third-party code that is permanently blocked, so only install extensions you trust.

### Add an optional background module

Create a module in **zegar_app/extensions/modules/** with a **create(settings)** factory. The returned service may implement **run(stop_event)** or **start()**, and should implement **close()** or **stop()** when it owns resources.

List its filename without .py under **[extensions] modules**. At most two configured background extensions are started.

## Fonts and bitmap images

### Fonts

The runtime reads BDF fonts. Bundled Matrix fonts are stored in:

- **zegar_app/assets/fonts/6-series/**
- **zegar_app/assets/fonts/8-series/**

Add custom BDF files to **zegar_app/assets/fonts/custom/**, then select a relative path in **[fonts]**. Built-in fallbacks are **BUILTIN:LCD_FONT** and **BUILTIN:TINY_FONT**.

The loader verifies that a font contains the digits and colon required by the clock. If a selected font cannot be loaded, the configured fallback is used.

### Monochrome images

Add 1-bit images under the configured **[assets] images_dir**. The lightweight loader supports:

- JSON bitmaps with width 1–64, height 8, and eight binary rows;
- plain PBM P1 files with a width of 1–64 and a height of 8.

No Pillow or NumPy import is needed for these image formats. See **assets/images/example_signal.json**.

## Optional features

### Bluetooth audio visualizer

The audio visualizer is included as an experimental optional module and is **disabled by default**:

~~~ini
[modules]
audio_visualizer = false
~~~

It requires a working Bluetooth A2DP source profile, PipeWire/WirePlumber routing, and the optional NumPy dependency. Enabling the setting alone does not configure the Bluetooth stack. The feature has not been verified on every Raspberry Pi / PipeWire combination; keep it disabled unless you have configured and tested the audio input path.

### Animations

Flip-clock and information transitions are optional and disabled by default. Enable them with **flip_clock** and **info_transitions** in **[modules]**. Keep them disabled on constrained hardware if you prefer the lowest overhead.

## Development and checks

Run the hardware-independent test suite:

~~~bash
./scripts/check.sh
~~~

The tests cover configuration parsing and reload, bitmap validation, the example sensor contract, and the custom-screen registry. They do not require a MAX7219 display or physical sensor.

Before testing the display manually, stop the systemd service to avoid two processes using the same SPI device.

## Troubleshooting

**The clock cannot open the display**

- Confirm SPI is enabled and /dev/spidev0.0 exists.
- Check that the service user belongs to the spi group.
- Confirm panel count and orientation match the physical chain.
- Check logs with **sudo journalctl -u malina-matrix -n 100 --no-pager**.

**The BME280 is not detected**

- Confirm I²C is enabled.
- Run **i2cdetect -y 1** and note whether the device appears at 0x76 or 0x77.
- Set **hardware.i2c_address** and **sensors.bme280** values accordingly.
- Install the base requirements inside the project's virtual environment.

**The browser dashboard has no history**

- Confirm [history] points to a writable database path and web directory.
- Check that web/data.json is being generated.
- Confirm Nginx (or another static server) serves the configured web directory.

**The controls do not reach the clock**

- Confirm the service is running and listening on the configured web port.
- Keep the browser and Raspberry Pi on the same trusted network.
- Check firewall rules for the dashboard and API ports.

## Data, privacy, and licensing

- Sensor readings are stored locally in SQLite.
- The dashboard history export is a local JSON file and is not included in Git.
- Weather coordinates are configurable and should be reviewed before publishing a personal configuration.
- No cloud account or API key is required for the default clock, sensor, or weather features.
- The main project is distributed under the MIT License. Bundled fonts and weather icons retain their third-party MIT notices in the asset directories.

## Build and wiring guide

New to the project? Start with **[Build guide: parts, wiring and first boot](docs/BUILD_GUIDE.md)**. It explains the reference hardware, the SPI and I²C connections, setup checks and first launch in a short, practical sequence.

## Detailed documentation\n\n- [Architecture and runtime lifecycle](docs/ARCHITECTURE.md)\n- [Hardware and wiring overview](docs/HARDWARE.md)\n- [Installation and service deployment](docs/INSTALLATION.md)\n- [Configuration reference](docs/CONFIGURATION.md)\n- [Writing sensor, screen and module extensions](docs/EXTENSIONS.md)\n\nContributions and new hardware backends are welcome. See **[CONTRIBUTING.md](CONTRIBUTING.md)**.
