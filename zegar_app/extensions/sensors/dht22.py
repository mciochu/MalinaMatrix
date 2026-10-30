"""Adafruit DHT22 temperature and humidity backend; imported only when enabled."""


class DHT22:
    def __init__(self, sensor):
        self.sensor = sensor

    def read(self):
        return {"temp": self.sensor.temperature, "hum": self.sensor.humidity}

    def close(self):
        close = getattr(self.sensor, "exit", None)
        if callable(close):
            close()


def create(settings):
    import board
    import adafruit_dht

    pin_name = settings.get("sensors.dht22", "pin", "D4").upper()
    pin = getattr(board, pin_name, None)
    if pin is None:
        raise ValueError(f"Unknown CircuitPython board pin: {pin_name}")
    return DHT22(adafruit_dht.DHT22(pin, use_pulseio=False))
