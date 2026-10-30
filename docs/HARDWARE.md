# Hardware

Malina Matrix targets Raspberry Pi OS / Debian on Raspberry Pi boards and a chain of MAX7219 8×8 LED matrix modules.

## Display chain

The default layout is eight chained 8×8 modules, producing a 64×8 pixel canvas. The number of panels, rotation, order and block orientation are configurable.

The MAX7219 uses the Raspberry Pi SPI interface. On the standard 40-pin header:

| MAX7219 signal | Raspberry Pi signal |
|---|---|
| DIN | SPI0 MOSI (GPIO 10, physical pin 19) |
| CLK | SPI0 SCLK (GPIO 11, physical pin 23) |
| CS / LOAD | SPI0 CE0 (GPIO 8, physical pin 24) |
| GND | Any GND |
| VCC | Supply suitable for the specific matrix modules |

Use a stable supply with enough current for the full LED chain. Connect grounds together. Some MAX7219 boards accept 3.3 V logic; others may require level shifting depending on their input circuitry. Check the module specifications rather than assuming every board is electrically identical. Avoid powering a large LED chain from the Raspberry Pi 3.3 V rail.

Enable SPI with `sudo raspi-config` → Interface Options → SPI. After reboot, check for `/dev/spidev0.0`.

## BME280 (I²C)

The default sensor backend is BME280 and reads temperature, relative humidity and pressure. The common I²C addresses are `0x76` and `0x77`.

On the standard Raspberry Pi header:

- SDA: GPIO 2 (physical pin 3)
- SCL: GPIO 3 (physical pin 5)
- power the sensor according to its breakout-board specification (3.3 V is the safe default for Pi I²C logic)
- connect GND to GND

Enable I²C and inspect the bus:

```bash
sudo raspi-config
sudo apt install -y i2c-tools
i2cdetect -y 1
```

Set the detected address in `[hardware] i2c_address` and `[sensors.bme280] address` if you are not using the default.

The application tries the selected BME280 backend and falls back across supported driver paths. Install the base dependencies from `requirements.txt`.

## Other supported sensor adapters

These adapters are included as optional extensions. Availability depends on the target hardware and the corresponding Python libraries.

| Sensor | Bus | Measurements | Setup |
|---|---|---|---|
| DS18B20 | 1-Wire GPIO | Temperature | Enable the Linux 1-Wire overlay; configure GPIO and the pull-up resistor per sensor documentation. |
| SHT31 | I²C | Temperature, humidity | Enable I²C and install the optional CircuitPython packages. |
| DHT22 | GPIO | Temperature, humidity | Configure a supported CircuitPython board pin and install the optional DHT package. |

The project’s current physical validation covers the MAX7219 display path and BME280 readings on the maintainer’s Raspberry Pi. The optional adapters are code implementations, not a guarantee that every clone board, cable or operating-system image will work without adjustment.

## Power and reliability

- Use an adequately rated 5 V supply for a multi-panel display.
- Keep SPI wiring short and secure.
- Do not hot-plug the display while the Raspberry Pi is powered.
- Check connector polarity before applying power.
- Ensure the Raspberry Pi, display and sensor grounds are common.
- If the display is unstable, test a single module first and then add panels.

## Display orientation

Use these settings in `zegar.conf`:

```ini
[hardware]
panel_count = 8
block_orientation = -90
rotation = 0
reverse_order = false
```

The correct orientation depends on the order and physical rotation of the individual modules. Change one setting at a time and test the result.
