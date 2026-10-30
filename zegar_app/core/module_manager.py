"""Lazy module lifecycle manager. Disabled modules are never imported."""
import importlib
import threading

from .plugin_loader import load_extension


class ModuleManager:
    def __init__(self, enabled, settings, logger=None):
        self.enabled = dict(enabled)
        self.settings = settings
        self.logger = logger or (lambda message: None)
        self._factories = {}
        self._instances = {}
        self._failed = set()
        self._extension_threads = []
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def register(self, name, module_path, factory_name):
        self._factories[name] = (module_path, factory_name)

    def get(self, name):
        if not self.enabled.get(name, False) or name in self._failed:
            return None
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            definition = self._factories.get(name)
            if definition is None:
                self.logger(f"Module '{name}' has no registered factory.")
                self._failed.add(name)
                return None
            module_path, factory_name = definition
            try:
                module = importlib.import_module(module_path)
                instance = getattr(module, factory_name)()
                self._instances[name] = instance
                self.logger(f"Module '{name}' initialized.")
                return instance
            except Exception as exc:
                self._failed.add(name)
                self.logger(f"Module '{name}' failed to initialize: {exc}")
                return None

    def load_extensions(self, names):
        """Start at most two explicitly enabled extensions outside the display loop."""
        for name in names[:2]:
            thread = threading.Thread(target=self._run_extension, args=(name,),
                                      daemon=True, name=f"module-{name}")
            self._extension_threads.append(thread)
            thread.start()

    def _run_extension(self, name):
        try:
            module = load_extension("modules", name)
            factory = getattr(module, "create", None)
            if not callable(factory):
                raise ValueError("module plugin must provide create(settings)")
            instance = factory(self.settings)
            if instance is None:
                raise ValueError("create(settings) returned None")
            with self._lock:
                self._instances[name] = instance
            run = getattr(instance, "run", None)
            start = getattr(instance, "start", None)
            if callable(run):
                run(self._stop)
            elif callable(start):
                start()
            else:
                self.logger(f"Module extension '{name}' has no run() or start() method.")
        except Exception as exc:
            self.logger(f"Module extension '{name}' failed: {exc}")

    def close(self):
        self._stop.set()
        with self._lock:
            instances = list(self._instances.values())
            self._instances.clear()
        for instance in instances:
            try:
                close = getattr(instance, "close", None)
                stop = getattr(instance, "stop", None)
                if callable(close):
                    close()
                elif callable(stop):
                    stop()
            except Exception as exc:
                self.logger(f"Module shutdown failed: {exc}")
        for thread in self._extension_threads:
            if thread.is_alive():
                thread.join(timeout=0.15)

[executed on device: malina (5f975671-b674-4ac4-965e-55c199641524)]