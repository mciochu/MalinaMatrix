# Hardware reference

This page separates the known reference build from generic connection guidance. Do not treat an unrecorded manufacturer or part number as a confirmed specification.

## Confirmed reference hardware

| Component | Confirmed model / specification | Notes |
|---|---|---|
| Raspberry Pi | **Raspberry Pi Zero W** | Main computer. This is the original Zero W, not a claim that the build uses a Zero 2 W. |
| LED matrix | **8 chained MAX7219 8×8 modules** | 64×8 logical display. Manufacturer and PCB revision are not recorded. |
| Environmental sensor | **BME280** | I²C temperature, humidity and pressure sensor. Exact breakout-board brand/model is unknown. |
| Display bus | SPI0 | Used by the MAX7219 chain. |
| Sensor bus | I²C bus 1 | Used by BME280. |
| Power supply | 5 V supply suitable for Raspberry Pi and display | Exact make, model and current rating are not recorded. Choose a supply based on the modules you actually use. |

## Typical Raspberry Pi Zero W connections

The following are the standard GPIO mappings for a Raspberry Pi Zero W with its 40-pin header. They describe the normal SPI0 and I²C1 wiring; confirm the physical connector orientation and your module labels before connecting anything.

### MAX7219 matrix chain — SPI0

| MAX7219 module pin | Raspberry Pi Zero W pin | GPIO |
|---|---:|---|
| DIN | Physical pin 19 | GPIO 10 / SPI0 MOSI |
| CLK | Physical pin 23 | GPIO 11 / SPI0 SCLK |
| CS / LOAD | Physical pin 24 | GPIO 8 / SPI0 CE0 |
| GND | Any GND pin, e.g. physical pin 6 | Ground |
| VCC | Suitable regulated supply input on the matrix module | Check the module specification |

Connect the Pi's MOSI, SCLK and CE0 signals to the input side of the first MAX7219 board. Chain each board's data output to the next board's data input as marked on the PCB. Do not connect the Pi to the output end of the chain.

### BME280 sensor — I²C1

| BME280 breakout pin | Raspberry Pi Zero W pin | GPIO |
|---|---:|---|
| SDA | Physical pin 3 | GPIO 2 / SDA1 |
| SCL | Physical pin 5 | GPIO 3 / SCL1 |
| GND | Any GND pin | Ground |
| VIN / VCC | According to breakout-board specification | Use a voltage supported by that specific breakout |

Many BME280 breakout boards accept 3.3 V; some include a regulator and level shifting. The exact board in the reference build is not identified, so check its documentation. Do not assume every breakout's VIN pin has the same requirements.

### Power and ground

- Use a stable 5 V supply appropriate for the Raspberry Pi and the total LED matrix load.
- Check the MAX7219 board's power input and current requirements. Eight modules can draw significantly more current at high brightness than a single module.
- Connect grounds together where the design requires a common reference.
- Do not power a large LED chain from the Pi's 3.3 V pin.
- Never hot-plug the matrix or sensor while the Pi is powered.

## Enable interfaces

On Raspberry Pi OS:

```bash
sudo raspi-config
```

Enable **SPI** and **I²C** in Interface Options, then reboot if requested.

Check SPI:

```bash
ls -l /dev/spidev*
```

Check the BME280 I²C address:

```bash
sudo apt update
sudo apt install -y i2c-tools
i2cdetect -y 1
```

Common BME280 addresses are `0x76` and `0x77`. Set the detected address in `zegar.conf`:

```ini
[hardware]
i2c_address = 0x76
i2c_port = 1

[sensors.bme280]
address = 0x76
port = 1
```

Use the address actually reported by your board; do not copy `0x76` blindly if the scan shows `0x77`.

## Optional sensor adapters

| Sensor | Bus / connection | Measurements | Reference-build status |
|---|---|---|---|
| DS18B20 | 1-Wire GPIO | Temperature | Driver included; not confirmed as connected in the reference build. |
| SHT31 | I²C | Temperature, humidity | Driver included; not confirmed as connected in the reference build. |
| DHT22 | GPIO | Temperature, humidity | Driver included; not confirmed as connected in the reference build. |

See [EXTENSIONS.md](EXTENSIONS.md) for software setup and [BUILD_GUIDE.md](BUILD_GUIDE.md) for the short assembly tutorial.
