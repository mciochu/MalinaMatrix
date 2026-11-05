"""SQLite-backed sensor history, bounded graph aggregation, and legacy JSON export."""
import datetime as dt
import json
import os
import sqlite3
import stat
import sys
import tempfile
import threading
import time

from .config import get_settings

_settings = get_settings()
DB_PATH = _settings.resolve_path(_settings.get("history", "database_path", "/home/mciochu/sensor_data.db"))
WEB_DIR = _settings.resolve_path(_settings.get("history", "web_directory", "/var/www/html"))

_RANGE_HOURS = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}
_MAX_HISTORY_ROWS = 50000
_SQLITE_TIMEOUT_SECONDS = 5.0

_export_lock = threading.Lock()
_log_lock = threading.Lock()
_last_error_log = {}

_cache_lock = threading.Lock()
_hourly_cache = []
_hourly_cache_updated = 0.0
_hourly_cache_hours = None
_hourly_cache_version = -1
_history_version = 0
_hourly_cache_ready = False
_hourly_cache_refresh_pending = set()
_hourly_cache_retry_at = {}


class HistoryRangeTooLarge(Exception):
    """Raised when a requested range exceeds the bounded API response size."""


def _connect():
    return sqlite3.connect(DB_PATH, timeout=_SQLITE_TIMEOUT_SECONDS)


def _log_limited(key, message, interval=300.0):
    now = time.monotonic()
    with _log_lock:
        previous = _last_error_log.get(key, 0.0)
        if now - previous < interval:
            return
        _last_error_log[key] = now
    print(message, file=sys.stderr)


def _format_reading(row):
    timestamp, temperature, humidity, pressure = row
    return {
        "timestamp": timestamp,
        "temperature": round(temperature, 1) if temperature is not None else None,
        "humidity": round(humidity) if humidity is not None else None,
        "pressure": round(pressure) if pressure is not None else None,
    }


def init_db():
    """Create the existing table if needed and add one non-unique time index."""
    conn = None
    try:
        conn = _connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                temperature REAL,
                humidity REAL,
                pressure REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp)"
        )
        conn.commit()
        return True
    except Exception as exc:
        _log_limited("database-init", f"Database init failed: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()


def log_to_db(temp, hum, press):
    """Persist one sensor sample; JSON publication is deliberately separate."""
    global _history_version
    conn = None
    try:
        conn = _connect()
        conn.execute(
            """
            INSERT INTO readings (temperature, humidity, pressure)
            VALUES (?, ?, ?)
            """,
            (temp, hum, press),
        )
        conn.commit()
        with _cache_lock:
            _history_version += 1
        return True
    except Exception as exc:
        _log_limited("database-write", f"Database log failed: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()


def export_json_for_web():
    """Atomically refresh the legacy JSON mirror only when its directory is writable.

    The running dashboard and LED graph use the range API/SQLite directly. On
    installations where the web root is not writable by the service account,
    this function leaves the existing data.json untouched instead of falling
    back to a non-atomic in-place write.
    """
    if not os.path.isdir(WEB_DIR):
        try:
            os.makedirs(WEB_DIR, exist_ok=True)
        except OSError as exc:
            _log_limited("json-export-permission", f"History JSON export unavailable: {exc}")
            return False

    if not os.access(WEB_DIR, os.W_OK | os.X_OK):
        _log_limited(
            "json-export-permission",
            f"History JSON export skipped: {WEB_DIR} is not writable; existing data.json was left unchanged.",
        )
        return False

    if not _export_lock.acquire(blocking=False):
        _log_limited("json-export-overlap", "History JSON export skipped: another export is already running.")
        return False

    temporary_path = None
    conn = None
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT datetime(timestamp, 'localtime'), temperature, humidity, pressure
            FROM readings NOT INDEXED
            WHERE timestamp >= datetime('now', '-30 days')
            ORDER BY timestamp ASC
            """
        ).fetchall()
        conn.close()
        conn = None

        data = [_format_reading(row) for row in rows]
        destination = os.path.join(WEB_DIR, "data.json")
        try:
            mode = stat.S_IMODE(os.stat(destination).st_mode)
        except FileNotFoundError:
            mode = 0o644

        fd, temporary_path = tempfile.mkstemp(
            prefix=".data.json.", suffix=".tmp", dir=WEB_DIR, text=True
        )
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary_path, destination)
        temporary_path = None

        directory_fd = os.open(WEB_DIR, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    except Exception as exc:
        _log_limited("json-export", f"Failed to publish history JSON: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
        _export_lock.release()


def get_history_range(range_key="30d"):
    """Return only a supported range, preserving the dashboard's local timestamp format.

    The range is relative to the newest stored reading, matching the former
    dashboard filter. Wide ranges deliberately use a table scan: tests on the
    current history showed it is faster than random table lookups through the
    time index for 7d/30d. Short ranges use the timestamp index.
    """
    if not isinstance(range_key, str) or range_key not in _RANGE_HOURS:
        raise ValueError("Unsupported history range")

    hours = _RANGE_HOURS[range_key]
    conn = None
    try:
        conn = _connect()
        latest_utc = conn.execute("SELECT MAX(timestamp) FROM readings").fetchone()[0]
        if latest_utc is None:
            return {"range": range_key, "count": 0, "latest": None, "data": []}

        latest_dt = dt.datetime.strptime(latest_utc, "%Y-%m-%d %H:%M:%S")
        cutoff_utc = (latest_dt - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        scan_hint = " NOT INDEXED" if hours >= 168 else ""
        query = (
            "SELECT datetime(timestamp, 'localtime'), temperature, humidity, pressure "
            "FROM readings" + scan_hint +
            " WHERE timestamp >= ? ORDER BY timestamp ASC, rowid ASC LIMIT ?"
        )
        rows = conn.execute(query, (cutoff_utc, _MAX_HISTORY_ROWS + 1)).fetchall()
        if len(rows) > _MAX_HISTORY_ROWS:
            raise HistoryRangeTooLarge("Requested history range is too large")

        data = [_format_reading(row) for row in rows]
        return {
            "range": range_key,
            "count": len(data),
            "latest": data[-1] if data else None,
            "data": data,
        }
    finally:
        if conn is not None:
            conn.close()


def get_latest_reading():
    """Return the newest stored sample, or None when the history is empty."""
    conn = None
    try:
        conn = _connect()
        row = conn.execute(
            """
            SELECT datetime(timestamp, 'localtime'), temperature, humidity, pressure
            FROM readings
            ORDER BY timestamp DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        return _format_reading(row) if row is not None else None
    finally:
        if conn is not None:
            conn.close()


def _compute_hourly_averages(hours):
    """Build the legacy 18 weighted buckets from a bounded SQLite range."""
    conn = None
    try:
        conn = _connect()
        latest_utc = conn.execute("SELECT MAX(timestamp) FROM readings").fetchone()[0]
        if latest_utc is None:
            rows = []
        else:
            latest_dt_utc = dt.datetime.strptime(latest_utc, "%Y-%m-%d %H:%M:%S")
            # Six extra hours cover local UTC-offset transitions while keeping the read bounded.
            query_start = (
                latest_dt_utc - dt.timedelta(hours=hours + 6)
            ).strftime("%Y-%m-%d %H:%M:%S")
            rows = conn.execute(
                """
                SELECT datetime(timestamp, 'localtime'), temperature, humidity, pressure
                FROM readings
                WHERE timestamp >= ?
                ORDER BY timestamp ASC, rowid ASC
                """,
                (query_start,),
            ).fetchall()
    finally:
        if conn is not None:
            conn.close()

    parsed = []
    for row in rows:
        try:
            parsed.append(
                (
                    dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"),
                    {
                        "temperature": row[1],
                        "humidity": row[2],
                        "pressure": row[3],
                    },
                )
            )
        except (TypeError, ValueError):
            continue

    if not parsed:
        return []

    last_dt = max(item[0] for item in parsed)
    cutoff = last_dt - dt.timedelta(hours=hours)
    bucket_count = 18
    bucket_secs = (hours * 3600) / bucket_count
    buckets = [{"temps": [], "hums": [], "press": []} for _ in range(bucket_count)]

    for sample_dt, record in parsed:
        elapsed = (sample_dt - cutoff).total_seconds()
        if elapsed < 0:
            continue
        index = min(bucket_count - 1, int(elapsed / bucket_secs))
        if 0 <= index < bucket_count:
            within_bucket = (elapsed - index * bucket_secs) / bucket_secs
            weight = 1.0 + 2.0 * min(1.0, max(0.0, within_bucket))
            for key, field, digits in (
                ("temps", "temperature", 1),
                ("hums", "humidity", 0),
                ("press", "pressure", 0),
            ):
                value = record.get(field)
                if value is not None:
                    try:
                        numeric = float(value)
                        # Legacy JSON rounded every source sample before weighting.
                        numeric = round(numeric, digits) if digits else round(numeric)
                        buckets[index][key].append((numeric, weight))
                    except (TypeError, ValueError):
                        pass

    def weighted_mean(samples):
        if not samples:
            return None
        weight_sum = sum(weight for _, weight in samples)
        return sum(value * weight for value, weight in samples) / weight_sum

    result = []
    for index, bucket in enumerate(buckets):
        temperature = weighted_mean(bucket["temps"])
        humidity = weighted_mean(bucket["hums"])
        pressure = weighted_mean(bucket["press"])
        result.append(
            {
                "slot": index,
                "temp": round(temperature, 1) if temperature is not None else None,
                "hum": round(humidity) if humidity is not None else None,
                "press": round(pressure) if pressure is not None else None,
            }
        )
    return result


def _populate_hourly_cache(hours):
    """Refresh the shared cache outside the display/rendering thread."""
    global _hourly_cache, _hourly_cache_updated, _hourly_cache_hours
    global _hourly_cache_version, _hourly_cache_ready

    with _cache_lock:
        version = _history_version

    try:
        result = _compute_hourly_averages(hours)
        with _cache_lock:
            # Never publish a result computed across a concurrent database insert.
            if version != _history_version:
                return False
            _hourly_cache = result
            _hourly_cache_updated = time.monotonic()
            _hourly_cache_hours = hours
            _hourly_cache_version = version
            _hourly_cache_ready = True
            _hourly_cache_retry_at.pop(hours, None)
        return True
    except Exception as exc:
        with _cache_lock:
            _hourly_cache_retry_at[hours] = time.monotonic() + 30.0
        _log_limited("led-history-refresh", f"LED history refresh failed: {type(exc).__name__}")
        return False


def refresh_hourly_cache(hours=6):
    """Precompute graph history synchronously from a non-render worker thread."""
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        return False
    if hours < 1 or hours > 168:
        return False

    with _cache_lock:
        if hours in _hourly_cache_refresh_pending:
            return False
        _hourly_cache_refresh_pending.add(hours)
    try:
        return _populate_hourly_cache(hours)
    finally:
        with _cache_lock:
            _hourly_cache_refresh_pending.discard(hours)


def _hourly_cache_worker(hours):
    try:
        _populate_hourly_cache(hours)
    finally:
        with _cache_lock:
            _hourly_cache_refresh_pending.discard(hours)


def get_hourly_averages(hours=6):
    """Return ready graph buckets only; never run SQLite on the display loop."""
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        return []
    if hours < 1 or hours > 168:
        return []

    now = time.monotonic()
    should_start_worker = False
    with _cache_lock:
        if (
            _hourly_cache_ready
            and _hourly_cache_hours == hours
            and _hourly_cache_version == _history_version
        ):
            return _hourly_cache

        # Keep the last valid graph on screen while a refreshed cache is prepared.
        cached = (
            _hourly_cache
            if _hourly_cache_ready and _hourly_cache_hours == hours
            else []
        )
        retry_at = _hourly_cache_retry_at.get(hours, 0.0)
        if hours not in _hourly_cache_refresh_pending and now >= retry_at:
            _hourly_cache_refresh_pending.add(hours)
            should_start_worker = True

    if should_start_worker:
        try:
            threading.Thread(
                target=_hourly_cache_worker,
                args=(hours,),
                daemon=True,
                name="history-graph-cache",
            ).start()
        except Exception as exc:
            with _cache_lock:
                _hourly_cache_refresh_pending.discard(hours)
                _hourly_cache_retry_at[hours] = time.monotonic() + 30.0
            _log_limited("led-history-worker", f"Could not start LED history worker: {type(exc).__name__}")
    return cached


[executed on device: malina (5f975671-b674-4ac4-965e-55c199641524)]