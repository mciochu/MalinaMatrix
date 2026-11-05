"""Cached Open-Meteo forecast and non-blocking refresh."""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import get_settings

_settings = get_settings()
WEATHER_LAT = _settings.number("weather", "latitude", 50.98, -90.0, 90.0)
WEATHER_LON = _settings.number("weather", "longitude", 21.24, -180.0, 180.0)
WEATHER_CACHE_SECONDS = _settings.integer("weather", "cache_seconds", 1800, 60, 86400)
WEATHER_RETRY_SECONDS = _settings.integer("weather", "retry_seconds", 300, 30, 86400)
WEATHER_TIMEOUT = _settings.number("weather", "request_timeout_seconds", 5.0, 1.0, 60.0)

RAIN_CODES = frozenset((51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82))
SNOW_CODES = frozenset((71, 73, 75, 77, 85, 86))
STORM_CODES = frozenset((95, 96, 99))


def weather_label(code):
    """Return the existing three-character weather abbreviation."""
    if code in (0, 1):
        return 'SLN'
    if code in (2, 3):
        return 'CHM'
    if code in (45, 48):
        return 'MGL'
    if code in RAIN_CODES:
        return 'DSZ'
    if code in SNOW_CODES:
        return 'SNG'
    if code in STORM_CODES:
        return 'BRZ'
    return 'CHM'


def _weather_code(hourly, index):
    codes = hourly.get("weather_code", hourly.get("weathercode", []))
    try:
        return int(codes[index])
    except (IndexError, TypeError, ValueError):
        return None


def _numeric_at(values, index):
    try:
        value = values[index]
        return float(value) if value is not None else None
    except (IndexError, TypeError, ValueError):
        return None


def select_precipitation_forecast(hourly, current_hour):
    """Pick the raw Open-Meteo probability for the wettest remaining forecast hour.

    No rain/snow probabilities are added or averaged. The selected value is
    exactly one hourly precipitation_probability value supplied by Open-Meteo.
    Only hours with a recognisable rain/snow forecast can determine the icon.
    current_hour must be an ISO local-hour string (YYYY-MM-DDTHH:00).
    """
    times = hourly.get("time", [])
    probabilities = hourly.get("precipitation_probability", [])
    rain = hourly.get("rain", [])
    snowfall = hourly.get("snowfall", [])
    best = None

    for index, forecast_time in enumerate(times):
        if not isinstance(forecast_time, str) or forecast_time < current_hour:
            continue
        probability = _numeric_at(probabilities, index)
        if probability is None:
            continue
        probability = max(0.0, min(100.0, probability))
        code = _weather_code(hourly, index)
        rain_amount = _numeric_at(rain, index) or 0.0
        snow_amount = _numeric_at(snowfall, index) or 0.0

        if code in SNOW_CODES:
            kind = "snow"
        elif code in RAIN_CODES:
            kind = "rain"
        elif code in STORM_CODES:
            if snow_amount > rain_amount:
                kind = "snow"
            elif rain_amount > 0:
                kind = "rain"
            else:
                continue
        elif snow_amount > 0:
            kind = "snow"
        elif rain_amount > 0:
            kind = "rain"
        else:
            continue

        if best is None or probability > best["probability"]:
            best = {"probability": probability, "kind": kind, "time": forecast_time}

    return best or {"probability": None, "kind": None, "time": None}


_weather_cache = None
_weather_cache_time = 0


def get_weather():
    """Fetch today's temperatures and the remaining-day hourly precipitation forecast."""
    global _weather_cache, _weather_cache_time
    now = time.time()
    if _weather_cache and (now - _weather_cache_time) < WEATHER_CACHE_SECONDS:
        return _weather_cache

    try:
        import urllib.request

        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
            f"&hourly=precipitation_probability,rain,snowfall,weather_code"
            f"&timezone=auto&forecast_days=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "MalinaMatrix/1.0"})
        with urllib.request.urlopen(req, timeout=WEATHER_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        daily = data.get("daily", {})
        hourly = data.get("hourly", {})
        offset = data.get("utc_offset_seconds", 0)
        try:
            local_now = datetime.now(timezone.utc) + timedelta(seconds=int(offset))
        except (TypeError, ValueError, OverflowError):
            local_now = datetime.now()
        current_hour = local_now.strftime("%Y-%m-%dT%H:00")
        precipitation = select_precipitation_forecast(hourly, current_hour)

        _weather_cache = {
            "temp_max": (daily.get("temperature_2m_max") or [None])[0],
            "temp_min": (daily.get("temperature_2m_min") or [None])[0],
            "code": (daily.get("weather_code", daily.get("weathercode")) or [3])[0],
            "precipitation_probability": precipitation["probability"],
            "precipitation_kind": precipitation["kind"],
            "precipitation_time": precipitation["time"],
        }
        _weather_cache_time = now
        return _weather_cache
    except Exception:
        if _weather_cache is None:
            _weather_cache = {
                "temp_max": None, "temp_min": None, "code": 3,
                "precipitation_probability": None,
                "precipitation_kind": None,
                "precipitation_time": None,
            }
        return _weather_cache


_weather_refresh_lock = threading.Lock()
_weather_refreshing = False
_weather_next_attempt = 0.0


def get_weather_nonblocking():
    """Return cached weather immediately and refresh stale data on a daemon thread."""
    global _weather_refreshing, _weather_next_attempt
    now = time.time()
    start_refresh = False
    with _weather_refresh_lock:
        cached = _weather_cache
        cache_fresh = cached is not None and (now - _weather_cache_time) < WEATHER_CACHE_SECONDS
        if not cache_fresh and not _weather_refreshing and now >= _weather_next_attempt:
            _weather_refreshing = True
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
                target=refresh_weather, daemon=True, name="weather-refresh"
            ).start()
        except Exception:
            with _weather_refresh_lock:
                _weather_refreshing = False

    return cached if cached is not None else {
        "temp_max": None, "temp_min": None, "code": 3,
        "precipitation_probability": None,
        "precipitation_kind": None,
        "precipitation_time": None,
    }

[executed on device: malina (5f975671-b674-4ac4-965e-55c199641524)]