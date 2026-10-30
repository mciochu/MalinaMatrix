"""Existing BME280 implementation exposed through the sensor plugin contract."""
from zegar_app.sensors import TemperatureReader


def create(settings):
    address = settings.get("sensors.bme280", "address", settings.get("hardware", "i2c_address", "0x76"))
    try:
        address = int(address, 0)
    except (TypeError, ValueError):
        address = 0x76
    port = settings.integer("sensors.bme280", "port", 1, 0, 16)
    driver = TemperatureReader(i2c_addr=address, i2c_port=port, verbose=False)
    if driver.backend is None:
        raise RuntimeError("no supported BME280 driver or I2C sensor was found")
    return driver