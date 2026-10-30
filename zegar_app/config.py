"""Lightweight, validated configuration with safe live reload support."""
import configparser
import math
import os
import threading
import time

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.environ.get("ZEGAR_CONFIG_PATH", os.path.join(_APP_ROOT, "zegar.conf"))


class Settings:
    """Read-only settings snapshot; parser replacement is atomic for readers."""

    def __init__(self, path=None):
        self.path = path or _CONFIG_PATH
        self.parser = self._new_parser()
        self._warned = set()
        self._reload_lock = threading.Lock()
        self._last_stat_check = 0.0
        self._fingerprint = None
        self._read_initial()

    @staticmethod
    def _new_parser():
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str.lower
        return parser

    @staticmethod
    def _file_fingerprint(path):
        try:
            stat = os.stat(path)
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def _read_initial(self):
        candidate = self._new_parser()
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                candidate.read_file(stream)
            self.parser = candidate
        except FileNotFoundError:
            self._warn("config-missing", f"Configuration file not found: {self.path}; built-in defaults will be used.")
        except (OSError, UnicodeError, configparser.Error) as exc:
            self._warn("config-read", f"Cannot read {self.path}: {exc}; built-in defaults will be used.")
        self._fingerprint = self._file_fingerprint(self.path)

    def _warn(self, key, message):
        if key in self._warned:
            return
        self._warned.add(key)
        try:
            import sys
            print(f"[CONFIG] {message}", file=sys.stderr)
        except Exception:
            pass

    def reload_if_changed(self, force=False, min_interval=2.0):
        """Reload only after a file change. Called from the main loop, never starts a thread."""
        now = time.monotonic()
        if not force and now - self._last_stat_check < min_interval:
            return False
        self._last_stat_check = now
        fingerprint = self._file_fingerprint(self.path)
        if fingerprint is None or fingerprint == self._fingerprint:
            return False
        if fingerprint[1] <= 0:
            self._warn("config-empty", "Ignoring an empty configuration file; keeping the previous settings.")
            self._fingerprint = fingerprint
            return False

        with self._reload_lock:
            candidate = self._new_parser()
            try:
                with open(self.path, "r", encoding="utf-8") as stream:
                    candidate.read_file(stream)
                if not candidate.sections():
                    raise configparser.Error("configuration has no sections")
            except (OSError, UnicodeError, configparser.Error) as exc:
                self._warn(("reload", fingerprint), f"Rejected configuration update: {exc}; previous settings remain active.")
                self._fingerprint = fingerprint
                return False

            # The parser is never mutated after publication.
            self.parser = candidate
            self._fingerprint = fingerprint
            self._warned.clear()
            print("[CONFIG] Configuration reloaded.", file=__import__("sys").stderr)
            return True

    def get(self, section, key, default):
        try:
            return self.parser.get(section, key, fallback=default).strip()
        except (configparser.Error, AttributeError) as exc:
            self._warn((section, key), f"{section}.{key}: {exc}; using {default!r}")
            return default

    def boolean(self, section, key, default):
        raw = self.get(section, key, str(default))
        value = str(raw).strip().lower()
        if value in ("1", "true", "yes", "on"):
            return True
        if value in ("0", "false", "no", "off"):
            return False
        self._warn((section, key), f"{section}.{key}={raw!r} is not a boolean; using {default}")
        return bool(default)

    def integer(self, section, key, default, minimum=None, maximum=None):
        raw = self.get(section, key, str(default))
        try:
            value = int(str(raw), 0) if str(raw).lower().startswith("0x") else int(raw)
        except (TypeError, ValueError):
            self._warn((section, key), f"{section}.{key}={raw!r} is not an integer; using {default}")
            return default
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            self._warn((section, key), f"{section}.{key}={value} is outside the allowed range; using {default}")
            return default
        return value

    def number(self, section, key, default, minimum=None, maximum=None):
        raw = self.get(section, key, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            self._warn((section, key), f"{section}.{key}={raw!r} is not a number; using {default}")
            return default
        if not math.isfinite(value):
            self._warn((section, key), f"{section}.{key}={raw!r} is not finite; using {default}")
            return default
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            self._warn((section, key), f"{section}.{key}={value} is outside the allowed range; using {default}")
            return default
        return value

    def items(self, section):
        try:
            return dict(self.parser.items(section))
        except configparser.Error:
            return {}

    def list(self, section, key, default=()):
        fallback = ",".join(default) if not isinstance(default, str) else default
        raw = self.get(section, key, fallback)
        return [part.strip().lower() for part in str(raw).split(",") if part.strip()]

    def resolve_path(self, value):
        path = os.path.expanduser(str(value))
        return path if os.path.isabs(path) else os.path.join(_APP_ROOT, path)


_instance_lock = threading.Lock()
_instance = None


def get_settings(reload=False):
    """Return the shared settings object. reload=True forces a safe file reload."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = Settings()
        instance = _instance
    if reload:
        instance.reload_if_changed(force=True, min_interval=0.0)
    return instance
