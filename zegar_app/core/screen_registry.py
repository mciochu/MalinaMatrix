"""Built-in and opt-in custom screen registry with isolated render workers."""
import threading
import time

from .plugin_loader import load_extension

_BUILTINS = {
    "temperature": (0, ("sensors",)),
    "humidity": (1, ("sensors",)),
    "pressure": (2, ("sensors",)),
    "weather": (3, ("weather",)),
}
_MAX_CUSTOM_SCREENS = 3


class _ScreenWorker:
    """Run custom rendering away from the MAX7219 drawing loop."""
    def __init__(self, name, render, refresh_seconds, stale_seconds, logger):
        self.name = name
        self.render = render
        self.refresh_seconds = refresh_seconds
        self.stale_seconds = stale_seconds
        self.logger = logger
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._context = None
        self._frame = None
        self._frame_time = 0.0
        self._next_request = 0.0
        self._busy = False
        self._busy_since = 0.0
        self._disabled = False
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _validate_frame(frame):
        if not isinstance(frame, (list, tuple)) or len(frame) != 8:
            raise ValueError("render(context) must return exactly 8 row bitmasks")
        rows = []
        for row in frame:
            if isinstance(row, bool) or not isinstance(row, int) or not 0 <= row <= 0xFFFFFFFFFFFFFFFF:
                raise ValueError("each row must be a non-negative integer bitmask")
            rows.append(row)
        return tuple(rows)

    def request(self, context):
        now = time.monotonic()
        with self._lock:
            if self._disabled or self._busy or now < self._next_request:
                return
            self._next_request = now + self.refresh_seconds
            self._context = dict(context)
            self._busy = True
            self._busy_since = now
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                name=f"screen-{self.name}")
                self._thread.start()
                self._event.set()
            else:
                self._event.set()

    def _run(self):
        while not self._stop.is_set():
            self._event.wait()
            self._event.clear()
            if self._stop.is_set():
                return
            with self._lock:
                context = self._context
                self._context = None
            if context is None:
                with self._lock:
                    self._busy = False
                continue
            started = time.monotonic()
            try:
                frame = self._validate_frame(self.render(context))
                elapsed = time.monotonic() - started
                with self._lock:
                    if self._disabled or self._stop.is_set():
                        self._busy = False
                        return
                    self._frame = frame
                    self._frame_time = time.monotonic()
                    self._busy = False
                    self._busy_since = 0.0
                if elapsed > self.stale_seconds:
                    self.logger(f"Custom screen '{self.name}' took {elapsed:.2f}s to render.")
            except Exception as exc:
                with self._lock:
                    self._disabled = True
                    self._busy = False
                    self._frame = None
                self.logger(f"Custom screen '{self.name}' disabled after an error: {exc}")
                return

    def frame(self):
        with self._lock:
            if not self._disabled and self._busy and self._busy_since and time.monotonic() - self._busy_since > self.stale_seconds:
                self._disabled = True
                self.logger(f"Custom screen '{self.name}' timed out and was disabled.")
            if self._disabled or self._frame is None:
                return None
            if time.monotonic() - self._frame_time > self.stale_seconds:
                return None
            return self._frame

    def close(self):
        self._stop.set()
        self._event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=0.15)


class ScreenRegistry:
    def __init__(self, settings, modules, logger=None):
        self.settings = settings
        self.modules = dict(modules)
        self.logger = logger or (lambda message: None)
        self.specs = {}
        self.mode_to_name = {}
        self.workers = {}
        for name, (mode, requirements) in _BUILTINS.items():
            self.specs[name] = {"mode": mode, "requires": requirements, "builtin": True}
            self.mode_to_name[mode] = name

        plugin_names = settings.list("screens", "plugins", ())
        if len(plugin_names) > _MAX_CUSTOM_SCREENS:
            self.logger(f"Only {_MAX_CUSTOM_SCREENS} custom screens may be enabled; extra entries are ignored.")
            plugin_names = plugin_names[:_MAX_CUSTOM_SCREENS]
        next_mode = 1000
        for plugin_name in plugin_names:
            try:
                module = load_extension("screens", plugin_name)
                screen_id = getattr(module, "SCREEN_ID", plugin_name).strip().lower()
                requirements = tuple(getattr(module, "REQUIRES", ()))
                render = getattr(module, "render", None)
                if not screen_id or screen_id in self.specs or not callable(render):
                    raise ValueError("SCREEN_ID must be unique and render(context) must be callable")
                missing = [item for item in requirements if not self.modules.get(item, False)]
                if missing:
                    self.logger(f"Custom screen '{screen_id}' skipped; disabled requirements: {', '.join(missing)}.")
                    continue
                refresh = settings.number("screens", "plugin_refresh_seconds", 2.0, 0.25, 60.0)
                stale = settings.number("screens", "plugin_stale_seconds", 15.0, 1.0, 300.0)
                self.specs[screen_id] = {"mode": next_mode, "requires": requirements,
                                         "builtin": False, "module": module}
                self.mode_to_name[next_mode] = screen_id
                self.workers[next_mode] = _ScreenWorker(screen_id, render, refresh, stale, self.logger)
                next_mode += 1
                self.logger(f"Custom screen '{screen_id}' loaded.")
            except Exception as exc:
                self.logger(f"Custom screen '{plugin_name}' could not be loaded: {exc}")

    def resolve_order(self, requested):
        result = []
        for name in requested:
            spec = self.specs.get(name)
            if spec is None:
                self.logger(f"Unknown or unavailable screen '{name}' was skipped.")
                continue
            if any(not self.modules.get(item, False) for item in spec["requires"]):
                continue
            mode = spec["mode"]
            if mode not in result:
                result.append(mode)
        if not result:
            for name in ("temperature", "humidity", "pressure", "weather"):
                spec = self.specs[name]
                if all(self.modules.get(item, False) for item in spec["requires"]):
                    result.append(spec["mode"])
        return result

    def request_custom_frame(self, mode, context):
        worker = self.workers.get(mode)
        if worker is None:
            return None
        worker.request(context)
        return worker.frame()

    def name_for_mode(self, mode):
        return self.mode_to_name.get(mode)

    def close(self):
        for worker in self.workers.values():
            worker.close()
