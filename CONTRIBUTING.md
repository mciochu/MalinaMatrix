# Contributing

Thanks for helping improve Malina Matrix. The project is intended to stay lightweight, understandable, and reliable on Raspberry Pi Zero-class hardware.

## Development setup

Use a Debian-based Linux machine or Raspberry Pi with Python 3.10 or later.

~~~bash
git clone https://github.com/mciochu/MalinaMatrix.git
cd MalinaMatrix
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp zegar.conf.example zegar.conf
~~~

The full display application requires Raspberry Pi SPI hardware to run. Hardware-independent checks can be run on a development computer:

~~~bash
./scripts/check.sh
~~~

## Design principles

- Keep the main display loop responsive.
- Do not perform sensor I/O, network I/O, disk exports, or custom extension work synchronously in the rendering loop.
- Disabled modules must not be imported or start threads/processes.
- Load optional dependencies lazily, inside the selected extension factory.
- Avoid adding large dependencies for simple display or bitmap operations.
- Validate configuration values and use safe defaults.
- Preserve the current MAX7219 renderer and existing data layout unless a change is explicitly necessary.

## Sensor extensions

Add a module under `zegar_app/extensions/sensors/`.

It must expose:

~~~python
def create(settings):
    return SensorDriver()


class SensorDriver:
    def read(self):
        return {"temp": 20.5, "hum": 45, "press": 1012}

    def close(self):
        pass
~~~

The returned dictionary may contain any combination of `temp`, `hum`, and `press`. Values must be finite numeric values. Hardware libraries should be imported inside `create(settings)`, not at module import time.

Enable the backend explicitly in `[sensors] enabled`. Keep sensor-specific options in a dedicated `[sensors.<name>]` section.

## Screen extensions

Add a module under `zegar_app/extensions/screens/` and list its filename (without `.py`) under `[screens] plugins`.

A screen exposes:

~~~python
SCREEN_ID = "my_screen"
REQUIRES = ("sensors",)


def render(context):
    return [0] * 8
~~~

The renderer returns exactly eight integer bitmasks. Bit 0 is the leftmost pixel. The current standard display width is 64 pixels, so a row may use up to 64 bits.

Custom screen code runs on a dedicated worker. Do not access the MAX7219 device or drawing context directly. Return a bitmap; the core renderer validates and copies it to the display.

## Optional background modules

Add modules under `zegar_app/extensions/modules/`. Each module must provide `create(settings)` and return a service object with `run(stop_event)` or `start()`. If it owns resources, implement `close()` or `stop()`.

Only explicitly configured extensions are loaded. Keep background work bounded and responsive to the stop event.

## Assets and fonts

- BDF fonts belong in `zegar_app/assets/fonts/custom/`.
- JSON or plain PBM P1 monochrome images belong in the configured asset image directory.
- Retain all relevant third-party license notices when adding assets.

## Pull requests

Before submitting a pull request:

1. Run `./scripts/check.sh`.
2. Test the change on real hardware when it affects SPI, I²C, MAX7219 rendering, or GPIO.
3. Explain configuration changes and whether they require a restart.
4. Include resource and licensing information for new assets.
5. Keep unrelated formatting or refactoring changes out of functional fixes.
