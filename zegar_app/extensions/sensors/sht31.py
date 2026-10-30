"""Adafruit SHT31 temperature and humidity backend; dependency is imported only when enabled."""


class SHT31:
    def __init__(self, sensor):
        self.sensor = sensor

    def read(self):
        return {"temp": self.sensor.temperature, "hum": self.sensor.relative_humidity}


def create(settings):
    import board
    import busio
    import adafruit_sht31d

    port = settings.integer("sensors.sht31", "port", 1, 0, 16)
    address = settings.integer("sensors.sht31", "address", 0x44, 0x03, 0x77)
    if port != 1:
        raise ValueError("This board backend currently supports the default CircuitPython I2C bus only")
    i2c = busio.I2C(board.SCL, board.SDA)
    return SHT31(adafruit_sht31d.SHT31D(i2c, address=address))