"""Non-blocking internet connectivity status for the display."""
import socket
import threading
import time
from .config import get_settings

_last_internet_check = 0.0
_last_internet_status = False
_internet_check_in_progress = False
_internet_check_lock = threading.Lock()
_settings = get_settings()
_INTERNET_CHECK_INTERVAL = _settings.number("network", "probe_interval_seconds", 10.0, 1.0, 3600.0)
_PROBE_HOST = _settings.get("network", "probe_host", "8.8.8.8")
_PROBE_PORT = _settings.integer("network", "probe_port", 53, 1, 65535)
_PROBE_TIMEOUT = _settings.number("network", "probe_timeout_seconds", 2.0, 0.1, 30.0)


def _probe_internet():
    """Sprawdź sieć w tle, aby timeout nie zatrzymywał rysowania matrycy."""
    global _last_internet_status, _internet_check_in_progress
    connected = False
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_PROBE_TIMEOUT)
        sock.connect((_PROBE_HOST, _PROBE_PORT))
        connected = True
    except Exception:
        connected = False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        with _internet_check_lock:
            _last_internet_status = connected
            _internet_check_in_progress = False


def check_internet():
    """Zwraca ostatni wynik od razu, a kontrolę łącza wykonuje asynchronicznie."""
    global _last_internet_check, _internet_check_in_progress
    now = time.monotonic()
    start_probe = False
    with _internet_check_lock:
        if (not _internet_check_in_progress and
                now - _last_internet_check >= _INTERNET_CHECK_INTERVAL):
            _last_internet_check = now
            _internet_check_in_progress = True
            start_probe = True
        status = _last_internet_status

    if start_probe:
        try:
            threading.Thread(
                target=_probe_internet,
                daemon=True,
                name="internet-check"
            ).start()
        except Exception:
            with _internet_check_lock:
                _internet_check_in_progress = False
    return status
