# Architecture

Malina Matrix keeps the MAX7219 renderer as the central runtime and places slower or optional work behind small service boundaries. The goal is a predictable clock loop on low-power Raspberry Pi hardware, with features that can be enabled independently.

## Runtime overview

```text
zegar.py
  └── zegar_app.main
       ├── config.Settings
       │    └── validated INI snapshot + safe reload
       └── zegar_app.display.run_clock
            ├── MAX7219 / SPI drawing loop
            ├── ModuleManager
            │    └── optional background extensions
            ├── SensorHub
            │    └── configured sensor drivers
            ├── ScreenRegistry
            │    └── custom screen workers
            ├── weather cache / refresh worker
            ├── history (SQLite + JSON export)
            ├── network probe
            └── HTTP control server
```

The compatibility entry point remains `zegar.py`; the implementation lives in the `zegar_app/` package. This keeps the systemd command simple and preserves the old import surface.

## Main components

| Component | Responsibility |
|---|---|
| `config.py` | Reads and validates INI settings, provides typed getters, resolves project-relative paths and publishes valid snapshots atomically. |
| `main.py` | Parses command-line arguments and starts the display runtime. |
| `display.py` | Owns the MAX7219 device, drawing helpers, screen scheduling, day/night behavior and main rendering loop. |
| `sensor_hub.py` | Loads only selected sensor backends, polls them on one worker and exposes the latest normalized values through a thread-safe snapshot. |
| `sensors.py` | Provides the BME280 reader with CircuitPython, SMBus and direct SMBus fallback paths. |
| `core/screen_registry.py` | Resolves built-in/custom screens, validates returned frames and schedules custom rendering outside the display loop. |
| `core/module_manager.py` | Lazily initializes optional modules and runs explicitly enabled background extensions. |
| `core/plugin_loader.py` | Loads a named extension from the expected extension package; it does not scan arbitrary folders. |
| `core/bitmap_assets.py` | Loads compact monochrome JSON and PBM P1 assets without a heavy image dependency. |
| `history.py` | Persists local sensor readings to SQLite, exports dashboard JSON and aggregates graph values. |
| `weather.py` | Caches Open-Meteo results and refreshes them asynchronously. |
| `network.py` | Checks network reachability without blocking the drawing loop. |
| `web_control.py` | Hosts the local HTTP API used by the browser dashboard. |
| `fonts.py` | Loads BDF fonts and locates bundled font assets. |

## Threading and responsiveness

The MAX7219 display is owned by the main runtime. Extensions should never initialize SPI or draw directly to the hardware.

- **Sensor polling:** one daemon worker reads the configured sensor backends. The display loop reads the latest cached values rather than waiting for I²C or 1-Wire.
- **Weather:** the screen uses the last cached forecast. An HTTP refresh runs in a separate worker and respects a request timeout and retry interval.
- **Custom screens:** each enabled screen gets a worker and returns a small 8-row bitmap. The registry validates its shape and value range before the main loop draws it.
- **Background extensions:** explicitly enabled modules run in their own worker. The manager requests shutdown through a stop event and calls an optional cleanup method.
- **Configuration:** the main loop checks the config file metadata periodically. An unchanged file is not reparsed. A candidate parser is built first and published only when the new configuration is valid.

Python cannot safely force-stop arbitrary code that is permanently blocked inside a thread. A plugin must therefore be trusted and should keep its operations bounded. The renderer does not wait synchronously for custom screen output, but this is not a process-level sandbox.

## Configuration lifecycle

The default config path is `zegar.conf` in the project root. Set `ZEGAR_CONFIG_PATH` to use another file, which is useful for system installations.

A valid configuration update is swapped atomically, so readers see either the old or the new snapshot. Invalid or empty updates leave the previous snapshot active. Invalid typed values use their documented fallback and are logged.

Display-level settings are designed for live reload. Hardware setup, imported modules, sensor drivers, plugin lists and HTTP listeners are initialized at startup and require a service restart when changed.

## Runtime data

The portable configuration stores the SQLite database under `data/sensor_data.db` and publishes the browser history as `web/data.json`. These are runtime outputs and must not be committed. The `.gitignore` excludes the local config, virtual environment, database, generated JSON and Python caches.

## Design rules for contributors

1. Keep sensor I/O, network I/O and disk exports out of the drawing loop.
2. Load optional dependencies only inside the selected feature or extension factory.
3. Never let plugins own the MAX7219 object.
4. Validate all values that cross an extension boundary.
5. Keep runtime data and host-specific settings outside version control.
6. Document which settings can be reloaded and which require a restart.
