"""Copy this file to add a sensor backend.

Required contract:
- create(settings) -> driver object
- driver.read() -> {"temp": number, "hum": number, "press": number}
- optional driver.close() -> release hardware resources

Use lazy imports inside create(). Never perform hardware work at module import time.
All read() calls happen on the SensorHub worker, never on the LED drawing loop.
"""
class ExampleSensor:
    def read(self):
        return {"temp": 21.5}


def create(settings):
    return ExampleSensor()
