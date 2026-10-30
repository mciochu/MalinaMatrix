# Build guide: parts, wiring and first boot

This is the short practical guide for assembling a clock similar to the maintainer's Malina Matrix reference build.

## 1. Parts list

### Used in the reference build

| Qty | Part | Model / specification | What it does |
|---:|---|---|---|
| 1 | Raspberry Pi | **Raspberry Pi Zero W** | Runs the clock software. |
| 8 | LED matrix modules | **MAX7219, 8×8 pixels each** | Eight modules are chained into one 64×8 display. |
| 1 | Environmental sensor | **BME280, I²C** | Provides temperature, humidity and pressure readings. |
| 1 | Power supply | Regulated 5 V supply suitable for the Pi and LED chain | Powers the system. The exact supply model used by the maintainer is not known. |
| as needed | Jumper wires / connectors | Compatible with the Pi 40-pin header and module terminals | Carry SPI, I²C, power and ground. |

**Known limitations of the parts list:** the manufacturer and exact PCB revision of the MAX7219 boards, the BME280 breakout-board brand/model, the power-supply make/current rating and the wire/connector part numbers were not recorded. The sensor chip model is BME280; that does not identify a particular breakout board.

### Optional alternatives supported by the software

- DS18B20 1-Wire temperature sensor.
- SHT31 I²C temperature/humidity sensor.
- DHT22 GPIO temperature/humidity sensor.

These are optional driver choices, not extra parts required for the reference build.

## 2. Connect the display

For the standard Raspberry Pi Zero W 40-pin header, connect the MAX7219 input board as follows:

| Raspberry Pi Zero W | MAX7219 |
|---|---|
| GPIO 10, physical pin 19 (MOSI) | DIN |
| GPIO 11, physical pin 23 (SCLK) | CLK |
| GPIO 8, physical pin 24 (CE0) | CS / LOAD |
| GND, e.g. physical pin 6 | GND |
| Suitable regulated supply | VCC |

The Pi's SPI signals go to the **input** of the first matrix module. Daisy-chain the remaining modules using the connectors labelled for data output/input on the boards. Keep the module order consistent with the configured panel order.

## 3. Connect the BME280

For I²C bus 1:

| Raspberry Pi Zero W | BME280 breakout |
|---|---|
| GPIO 2, physical pin 3 (SDA1) | SDA |
| GPIO 3, physical pin 5 (SCL1) | SCL |
| GND | GND |
| Appropriate 3.3 V / VIN supply | VIN / VCC, as specified by the breakout manufacturer |

The exact BME280 breakout model is unknown. Check whether your board accepts 3.3 V only or has a regulator/level shifter before applying power. Do not infer voltage compatibility from the BME280 chip name alone.

## 4. Check power and wiring before boot

1. Check the Pi and matrix supply polarity.
2. Make sure the power supply can handle the Raspberry Pi and all eight matrix modules.
3. Ensure a common ground where required.
4. Check that SPI and I²C signal wires are not swapped.
5. Do not connect or disconnect modules while powered.

If you are using a different MAX7219 board or power arrangement, follow that board's electrical documentation. This guide gives the signal mapping, not a verified wiring photograph or a specific power-supply recommendation.

## 5. Enable SPI and I²C

Run:

```bash
sudo raspi-config
```

Enable **SPI** and **I²C** under Interface Options, then reboot if requested.

Verify SPI:

```bash
ls -l /dev/spidev*
```

Install I²C tools and find the sensor:

```bash
sudo apt update
sudo apt install -y i2c-tools
i2cdetect -y 1
```

The BME280 commonly appears at address `0x76` or `0x77`. Use the address that your scan actually reports.

## 6. Install Malina Matrix

```bash
git clone https://github.com/mciochu/MalinaMatrix.git
cd MalinaMatrix
cp zegar.conf.example zegar.conf
```

Edit the hardware settings:

```ini
[hardware]
panel_count = 8
block_orientation = -90
rotation = 0
i2c_address = 0x76
i2c_port = 1

[sensors]
enabled = bme280

[sensors.bme280]
address = 0x76
port = 1
```

Change the I²C address if your sensor scan reports `0x77`. Adjust panel orientation if your physical matrix boards are mounted differently.

Install and start the service:

```bash
sudo ./scripts/install.sh
sudo systemctl status malina-matrix
```

Follow the startup log if something does not work:

```bash
sudo journalctl -u malina-matrix -f
```

## 7. Open the browser dashboard

The optional dashboard is served from the project's `web/` directory. Follow the [installation guide](INSTALLATION.md) to configure Nginx. The local control API defaults to port 8088 and is not authenticated, so keep it on a trusted local network.

## 8. What you should see

After a successful setup:

- the matrix displays the clock;
- the daytime clock uses the bundled MatrixChunky8X BDF font by default;
- the BME280 values can be shown on the matrix and in the dashboard;
- history and graph features use locally stored sensor readings;
- weather requires you to set your own latitude and longitude in `zegar.conf`.

The lamp mode uses the same matrix as a light surface. It is not a separate physical lamp device.

## Troubleshooting checklist

- **No matrix device:** check SPI is enabled and `/dev/spidev*` exists.
- **Blank or garbled matrix:** check DIN/CLK/CS wiring, module input direction, panel count and orientation.
- **No BME280 found:** enable I²C, run `i2cdetect -y 1`, and set the actual address.
- **Sensor values are unavailable:** confirm the breakout's supply voltage, SDA/SCL wiring and installed dependencies.
- **Service fails to start:** inspect `journalctl -u malina-matrix -n 100 --no-pager`.

For detailed pinout and extension information, continue to [HARDWARE.md](HARDWARE.md), [INSTALLATION.md](INSTALLATION.md) and [EXTENSIONS.md](EXTENSIONS.md).
