# Configuration reference

Malina Matrix reads an INI configuration file. By default it is `zegar.conf` in the project root. Set `ZEGAR_CONFIG_PATH=/path/to/file.conf` to use another location.

Start from `zegar.conf.example`. The example is safe to commit; the local `zegar.conf` is ignored by Git because it may contain local coordinates, paths or other host-specific settings.

## General rules

- Booleans accept `true/false`, `yes/no`, `on/off` and `1/0`.
- Invalid values and out-of-range numbers use safe defaults and are logged.
- Relative paths are resolved from the project root.
- A syntactically invalid or empty live update is rejected; the previous valid snapshot remains active.
- The config file is checked periodically using modification time and size, avoiding repeated parsing when unchanged.

## Sections

| Section | Keys | Description |
|---|---|---|
| `[modules]` | `sensors`, `history`, `graph`, `weather`, `wifi_indicator`, `web_control`, `messages`, `lamp`, `audio_visualizer`, `flip_clock`, `info_transitions` | Enables or disables built-in runtime modules. Optional audio and animations default to off. |
| `[hardware]` | `panel_count`, `block_orientation`, `rotation`, `reverse_order`, `i2c_address`, `i2c_port` | Matrix chain and I²C bus settings. |
| `[clock]` | `format_24h`, `show_seconds` | Clock display format. |
| `[fonts]` | `day`, `sensor`, `night`, `message`, `fallback`, `sensor_fallback` | BDF file paths or built-in font identifiers. |
| `[display]` | `screen_order`, `screen_dwell_seconds`, `normal_refresh_seconds`, `message_refresh_seconds`, `animation_refresh_seconds`, `night_mode_enabled`, `night_start_hour`, `night_end_hour` | Screen schedule, refresh and day/night behavior. |
| `[brightness]` | `day_contrast`, `night_contrast`, `lamp_default_brightness`, `lamp_default_density` | MAX7219 intensity and initial lamp settings. |
| `[sensor]` | `refresh_seconds` | Sensor worker polling interval. |
| `[sensors]` | `enabled` | Comma-separated names of sensor adapters to load. |
| `[sensors.bme280]` | `address`, `port` | BME280 I²C address and bus. |
| `[sensors.ds18b20]` | `device_id` | 1-Wire device ID or `auto`. |
| `[sensors.sht31]` | `address`, `port` | SHT31 I²C address and bus. |
| `[sensors.dht22]` | `pin` | CircuitPython board pin identifier. |
| `[history]` | `database_path`, `web_directory`, `log_interval_seconds`, `graph_hours`, `export_on_start` | SQLite storage and dashboard JSON output. |
| `[weather]` | `latitude`, `longitude`, `cache_seconds`, `retry_seconds`, `request_timeout_seconds`, `display_style` | Open-Meteo forecast location and cache behavior. |
| `[network]` | `probe_host`, `probe_port`, `probe_timeout_seconds`, `probe_interval_seconds` | Internet reachability probe. |
| `[web]` | `host`, `port`, `message_duration_seconds` | Local HTTP control server. |
| `[screens]` | `plugins`, `plugin_refresh_seconds`, `plugin_stale_seconds` | Enabled custom screens and worker timing. |
| `[extensions]` | `modules` | Explicitly enabled background extensions. |
| `[effects]` | `flip_seconds`, `flip_frame_seconds`, `info_transition_seconds`, `info_blank_seconds`, `info_frame_seconds` | Optional animation timing. |
| `[assets]` | `images_dir` | Directory containing user JSON/PBM bitmap assets. |

## Font values

Font entries accept:

- a path to a BDF file, relative to the project root or absolute;
- `BUILTIN:LCD_FONT`;
- `BUILTIN:TINY_FONT`.

Bundled BDF files are in `zegar_app/assets/fonts/6-series/` and `8-series/`. Custom fonts belong in `zegar_app/assets/fonts/custom/`.

## Screen order

Built-in screen names:

- `temperature`
- `humidity`
- `pressure`
- `weather`

Custom screens are appended to the requested order only when listed under `[screens] plugins` and when their required modules are enabled.

## Examples

Enable two sensor drivers:

```ini
[sensors]
enabled = bme280, ds18b20
```

Display only humidity, temperature and weather:

```ini
[display]
screen_order = humidity, temperature, weather
screen_dwell_seconds = 8
```

Use an alternate BDF font:

```ini
[fonts]
day = zegar_app/assets/fonts/8-series/MatrixLight8X.bdf
```

Disable network-heavy or optional features:

```ini
[modules]
weather = false
wifi_indicator = false
audio_visualizer = false
```

## Live reload versus restart

These settings are designed to apply without a restart: font selection, brightness, order of already loaded screens, timing values, clock format, night schedule, weather display style and history interval.

Restart the service after changing hardware initialization, module enablement, sensor drivers, the web host/port, or the configured custom screen/background extension list. The runtime intentionally does not replace live SPI/I²C objects or HTTP listeners in place.

## Security notes

The web control API is unauthenticated. Binding to `0.0.0.0` makes it reachable on network interfaces; use a trusted local network, firewall access to the configured port and avoid direct Internet exposure.
