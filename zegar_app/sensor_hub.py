"""Non-blocking sensor coordinator with a small, explicit plugin registry."""
import math
import threading
import time

from .core.plugin_loader import load_extension

_ALLOWED_FIELDS = {"temp", "hum", "press"}
_MAX_BACKENDS = 4


class SensorHub:
    """Poll configured backends on one daemon worker; the display loop only reads cached values."""
    def __init__(self, settings, logger=None):
        self.settings = settings
        self.logger = logger or (lambda message: None)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest = {}
        self._last_success = 0.0
        self._thread = None
        self._started = False
        self._drivers = []
        self._closed = False
        self._last_error_log = {}

    def start(self):
        if self._started or self._closed:
            return
        if not self.settings.list("sensors", "enabled", ("bme280",)):
            self.logger("No sensor backends are configured; sensor polling is disabled.")
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="sensor-hub")
        self._thread.start()

    def _load_backends(self):
        names = self.settings.list("sensors", "enabled", ("bme280",))[:_MAX_BACKENDS]
        for name in names:
            try:
                plugin = load_extension("sensors", name)
                factory = getattr(plugin, "create", None)
                if not callable(factory):
                    raise ValueError("sensor plugin must provide create(settings)")
                driver = factory(self.settings)
                if driver is None or not callable(getattr(driver, "read", None)):
                    raise ValueError("sensor plugin did not return an object with read()")
                self._drivers.append((name, driver))
                self.logger(f"Sensor backend '{name}' initialized.")
            except Exception as exc:
                self.logger(f"Sensor backend '{name}' unavailable: {exc}")

    def _normalize(self, values):
        if not isinstance(values, dict):
            raise ValueError("sensor read() must return a dictionary")
        clean = {}
        for key, raw in values.items():
            if key not in _ALLOWED_FIELDS or raw is None or isinstance(raw, bool):
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            clean[key] = round(value, 1) if key == "temp" else round(value)
        return clean

    def _run(self):
        self._load_backends()
        if not self._drivers:
            return
        interval = self.settings.number("sensor", "refresh_seconds", 1.0, 0.25, 3600.0)
        while not self._stop.is_set():
            merged = {}
            for name, driver in self._drivers:
                if self._stop.is_set():
                    break
                try:
                    sample = driver.read()
                    if sample is not None:
                        merged.update(self._normalize(sample))
                except Exception as exc:
                    now = time.monotonic()
                    if now - self._last_error_log.get(name, 0.0) >= 60.0:
                        self.logger(f"Sensor backend '{name}' read failed: {exc}")
                        self._last_error_log[name] = now
            if merged:
                with self._lock:
                    self._latest.update(merged)
                    self._last_success = time.monotonic()
            interval = self.settings.number("sensor", "refresh_seconds", interval, 0.25, 3600.0)
            self._stop.wait(interval)
        for _, driver in self._drivers:
            close = getattr(driver, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    self.logger(f"Sensor backend cleanup failed: {exc}")

    def snapshot(self):
        with self._lock:
            return dict(self._latest)

    @property
    def last_success(self):
        with self._lock:
            return self._last_success

    def close(self):
        self._closed = True
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=0.25)
