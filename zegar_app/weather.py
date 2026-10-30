"""Cached weather data and non-blocking forecast refresh."""
import json
import threading
import time
from .config import get_settings

# ============================================================
# POGODA (Open-Meteo, darmowe API bez klucza)
# ============================================================
_settings = get_settings()
WEATHER_LAT = _settings.number("weather", "latitude", 0.0, -90.0, 90.0)
WEATHER_LON = _settings.number("weather", "longitude", 0.0, -180.0, 180.0)
WEATHER_CACHE_SECONDS = _settings.integer("weather", "cache_seconds", 1800, 60, 86400)
WEATHER_RETRY_SECONDS = _settings.integer("weather", "retry_seconds", 300, 30, 86400)
WEATHER_TIMEOUT = _settings.number("weather", "request_timeout_seconds", 5.0, 1.0, 60.0)

# Opisy pogody (3-literowe skróty)
def weather_label(code):
    if code in (0, 1):                          return 'SLN'
    elif code in (2, 3):                        return 'CHM'
    elif code in (45, 48):                      return 'MGL'
    elif code in (51,53,55,56,57,61,63,65,66,67,80,81,82): return 'DSZ'
    elif code in (71,73,75,77,85,86):           return 'SNG'
    elif code in (95,96,99):                    return 'BRZ'
    return 'CHM'

_weather_cache = None
_weather_cache_time = 0


def get_weather():
    """Pobiera prognozę na dziś z Open-Meteo. Cache 30 min."""
    global _weather_cache, _weather_cache_time
    now = time.time()
    if _weather_cache and (now - _weather_cache_time) < WEATHER_CACHE_SECONDS:
        return _weather_cache

    try:
        import urllib.request
        url = (f"https://api.open-meteo.com/v1/forecast?"
               f"latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
               f"&daily=temperature_2m_max,temperature_2m_min,weathercode"
               f"&timezone=auto&forecast_days=1")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=WEATHER_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        daily = data.get('daily', {})
        _weather_cache = {
            'temp_max': daily.get('temperature_2m_max', [None])[0],
            'temp_min': daily.get('temperature_2m_min', [None])[0],
            'code': daily.get('weathercode', [0])[0],
        }
        _weather_cache_time = now
        return _weather_cache
    except Exception:
        if _weather_cache is None:
            _weather_cache = {'temp_max': None, 'temp_min': None, 'code': 3}
        return _weather_cache


_weather_refresh_lock = threading.Lock()
_weather_refreshing = False
_weather_next_attempt = 0.0


def get_weather_nonblocking():
    """Zwraca dostępny cache od razu; odświeżenie prognozy wykonuje w tle."""
    global _weather_refreshing, _weather_next_attempt
    now = time.time()
    start_refresh = False
    with _weather_refresh_lock:
        cached = _weather_cache
        cache_fresh = cached is not None and (now - _weather_cache_time) < WEATHER_CACHE_SECONDS
        if (not cache_fresh and not _weather_refreshing and
                now >= _weather_next_attempt):
            _weather_refreshing = True
            # Przy błędzie sieciowym ponów próbę dopiero po 5 minutach.
            _weather_next_attempt = now + WEATHER_RETRY_SECONDS
            start_refresh = True

    if start_refresh:
        def refresh_weather():
            global _weather_refreshing
            try:
                get_weather()
            except Exception:
                pass
            finally:
                with _weather_refresh_lock:
                    _weather_refreshing = False

        try:
            threading.Thread(
                target=refresh_weather,
                daemon=True,
                name="weather-refresh"
            ).start()
        except Exception:
            with _weather_refresh_lock:
                _weather_refreshing = False

    # Przy pierwszym uruchomieniu może jeszcze nie być prognozy. Nie czekaj na sieć.
    return cached if cached is not None else {
        'temp_max': None,
        'temp_min': None,
        'code': 3
    }
