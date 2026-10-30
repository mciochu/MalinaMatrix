# Extensions

Extensions let users add sensors, display screens and background services without editing the MAX7219 rendering loop.

Only names explicitly configured in `zegar.conf` are loaded. Python files in an extension directory are not automatically imported.

## Sensor backend contract

Location: `zegar_app/extensions/sensors/`

A sensor plugin exposes a factory:

```python
def create(settings):
    return SensorDriver()
```

The returned object must expose `read()`. It may expose `close()` for resource cleanup.

```python
class SensorDriver:
    def read(self):
        return {
            "temp": 21.5,
            "hum": 48.0,
            "press": 1012.4,
        }

    def close(self):
        pass
```

The returned dictionary may contain any combination of:

- `temp`: temperature in degrees Celsius;
- `hum`: relative humidity in percent;
- `press`: pressure in hPa.

Values must be finite numeric values. Unknown keys, booleans, non-numeric values and NaN/Infinity are ignored by the normalizer.

Enable backends explicitly:

```ini
[sensors]
enabled = bme280, ds18b20

[sensors.bme280]
address = 0x76
port = 1

[sensors.ds18b20]
device_id = auto
```

The registry currently accepts up to four configured sensor backends. Each backend is imported only after it is selected. Sensor polling runs on a single worker thread, not in the display loop.

### Built-in backends

| Name | Hardware | Required packages |
|---|---|---|
| `bme280` | I²C BME280 | Base SMBus dependencies; CircuitPython path is optional |
| `ds18b20` | Linux 1-Wire DS18B20 | No extra Python package when the kernel device is available |
| `sht31` | I²C SHT31 | `adafruit-blinka`, `adafruit-circuitpython-sht31d` |
| `dht22` | GPIO DHT22 | `adafruit-blinka`, `adafruit-circuitpython-dht` |

Install optional dependencies using `pip install -r requirements-optional.txt`, or install only the packages needed for the sensor you selected.

## Custom screen contract

Location: `zegar_app/extensions/screens/`

A screen module exposes a unique ID, optional module requirements and a render function:

```python
SCREEN_ID = "example_status"
REQUIRES = ("sensors",)

def render(context):
    rows = [0] * 8
    rows[7] = 0x3F
    return rows
```

Enable it by filename without `.py`:

```ini
[screens]
plugins = example_status

[display]
screen_order = temperature, example_status, weather
```

The renderer receives a context dictionary with the latest available application data and matrix dimensions. It must return exactly eight integer row masks. For the default 64×8 canvas, bit 0 is the leftmost pixel and bit 63 is the rightmost pixel. Invalid dimensions, negative values or masks wider than the display are rejected.

The registry allows up to three custom screens. Each screen is called on its own worker at the configured interval:

```ini
[screens]
plugin_refresh_seconds = 2.0
plugin_stale_seconds = 15.0
```

The main renderer only consumes the last validated bitmap and does not wait for a slow render call. When a plugin throws an exception or its frame becomes stale, the registry disables that screen and records a diagnostic message. A Python thread is not a hard security boundary and cannot be forcibly stopped safely if third-party code blocks forever; only install code you trust.

## Background module contract

Location: `zegar_app/extensions/modules/`

A background extension exports `create(settings)`. It returns an object that implements either `run(stop_event)` or `start()`. It should also provide `close()` or `stop()` when it owns resources.

```python
class ExampleService:
    def run(self, stop_event):
        while not stop_event.is_set():
            # Keep work short and wait interruptibly between iterations.
            stop_event.wait(5.0)

    def close(self):
        pass

def create(settings):
    return ExampleService()
```

Configure it explicitly:

```ini
[extensions]
modules = example_service
```

At most two background extensions are started. The manager signals shutdown through a stop event and invokes the optional cleanup method.

## Bitmap assets

Place monochrome images in the directory configured by `[assets] images_dir`. The loader supports:

- JSON objects with `width` (1–64), `height = 8` and exactly eight rows;
- PBM plain-text `P1` files with width 1–64 and height 8.

Rows may be represented as strings of `0` and `1`, or as integer bitmasks in JSON. The loader rejects invalid names and malformed images. The example file is `zegar_app/assets/images/example_signal.json`.

## Font assets

The runtime uses BDF fonts. Bundled fonts are grouped into `6-series` and `8-series`; place custom BDF files in `zegar_app/assets/fonts/custom/`.

Select a font path under `[fonts]`. Built-in fallbacks are `BUILTIN:LCD_FONT` and `BUILTIN:TINY_FONT`. A missing or invalid font falls back safely.

## Plugin development checklist

1. Import hardware dependencies inside `create(settings)`, not at module import time.
2. Keep I/O bounded and handle hardware errors.
3. Do not import or manipulate the MAX7219 display device.
4. Return only normalized sensor fields or an 8-row bitmap.
5. Implement cleanup for open file handles, buses and GPIO resources.
6. Test on the Raspberry Pi hardware before relying on the extension in continuous operation.
7. Keep third-party license notices with bundled assets.
