"""Linux 1-Wire DS18B20 temperature sensor backend (no extra Python package)."""
import glob
import os


class DS18B20:
    def __init__(self, path):
        self.path = path

    def read(self):
        with open(self.path, "r", encoding="ascii") as stream:
            first, second = stream.read().splitlines()[:2]
        if not first.rstrip().endswith("YES") or "t=" not in second:
            return None
        raw = int(second.split("t=", 1)[1])
        return {"temp": raw / 1000.0}


def create(settings):
    device_id = settings.get("sensors.ds18b20", "device_id", "auto")
    if device_id == "auto":
        matches = sorted(glob.glob("/sys/bus/w1/devices/28-*/w1_slave"))
        if not matches:
            raise RuntimeError("no DS18B20 device found under /sys/bus/w1/devices")
        path = matches[0]
    else:
        if not device_id.startswith("28-") or "/" in device_id or ".." in device_id:
            raise ValueError("device_id must be 'auto' or a valid 28-xxxxxxxxxxxx ID")
        path = f"/sys/bus/w1/devices/{device_id}/w1_slave"
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return DS18B20(path)
