"""SQLite readings, web JSON export, and graph aggregation."""
import json
import os
import sqlite3
import sys
import time
from .config import get_settings

DB_PATH = get_settings().resolve_path(get_settings().get("history", "database_path", "data/sensor_data.db"))
WEB_DIR = get_settings().resolve_path(get_settings().get("history", "web_directory", "web"))

def init_db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                temperature REAL,
                humidity REAL,
                pressure REAL
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database init failed: {e}", file=sys.stderr)

def log_to_db(temp, hum, press):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO readings (temperature, humidity, pressure)
            VALUES (?, ?, ?)
        """, (temp, hum, press))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database log failed: {e}", file=sys.stderr)

def export_json_for_web():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Pobierz dane z ostatnich 30 dni (czas lokalny)
        cursor.execute("""
            SELECT datetime(timestamp, 'localtime'), temperature, humidity, pressure 
            FROM readings 
            WHERE timestamp >= datetime('now', '-30 days')
            ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()
        conn.close()

        data = []
        for row in rows:
            data.append({
                'timestamp': row[0],
                'temperature': round(row[1], 1) if row[1] is not None else None,
                'humidity': round(row[2]) if row[2] is not None else None,
                'pressure': round(row[3]) if row[3] is not None else None
            })

        # Upewnij się, że katalog istnieje i zapisz plik JSON.
        os.makedirs(WEB_DIR, exist_ok=True)
        with open(os.path.join(WEB_DIR, "data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to export JSON to {WEB_DIR}: {e}", file=sys.stderr)

# Cache dla wykresu słupkowego (ostatnie 6h, 18 słupków co ~20min) — dane z data.json
_hourly_cache = []
_hourly_cache_updated = 0

def get_hourly_averages(hours=6):
    """Zwraca 18 przedziałów czasowych ze średnimi ważonymi dla ostatnich N godzin.
    Nowsze próbki w każdym przedziale mają większy wpływ na wysokość słupka.
    Wynik jest odświeżany co 15 s; najnowszy odczyt czujnika jest dodawany na żywo w wykresie."""
    global _hourly_cache, _hourly_cache_updated
    now = time.time()
    if _hourly_cache and (now - _hourly_cache_updated) < 15:
        return _hourly_cache

    json_path = os.path.join(WEB_DIR, "data.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            return _hourly_cache or []

        from datetime import datetime, timedelta
        # Nie zakładaj, że ostatni element pliku ma najnowszy timestamp.
        parsed = []
        for record in data:
            try:
                parsed.append((datetime.strptime(record['timestamp'], "%Y-%m-%d %H:%M:%S"), record))
            except (KeyError, TypeError, ValueError):
                continue
        if not parsed:
            return _hourly_cache or []
        last_dt = max(item[0] for item in parsed)
        cutoff = last_dt - timedelta(hours=hours)

        bucket_count = 18  # zachowaj szerokość wykresu: 18 pikseli
        bucket_secs = (hours * 3600) / bucket_count
        buckets = [{'temps': [], 'hums': [], 'press': []} for _ in range(bucket_count)]

        for dt, r in parsed:
            elapsed = (dt - cutoff).total_seconds()
            if elapsed < 0:
                continue
            # Włącz także najnowszy rekord dokładnie na prawej krawędzi 6h.
            idx = min(bucket_count - 1, int(elapsed / bucket_secs))
            if 0 <= idx < bucket_count:
                # Waga rośnie od początku do końca 20-minutowego przedziału (1x–3x).
                within_bucket = (elapsed - idx * bucket_secs) / bucket_secs
                weight = 1.0 + 2.0 * min(1.0, max(0.0, within_bucket))
                for key, field in (("temps", "temperature"), ("hums", "humidity"), ("press", "pressure")):
                    value = r.get(field)
                    if value is not None:
                        try:
                            buckets[idx][key].append((float(value), weight))
                        except (TypeError, ValueError):
                            pass

        def weighted_mean(samples):
            if not samples:
                return None
            weight_sum = sum(weight for _, weight in samples)
            return sum(value * weight for value, weight in samples) / weight_sum

        result = []
        for i, b in enumerate(buckets):
            temp = weighted_mean(b['temps'])
            hum = weighted_mean(b['hums'])
            press = weighted_mean(b['press'])
            result.append({
                'slot': i,
                'temp': round(temp, 1) if temp is not None else None,
                'hum': round(hum) if hum is not None else None,
                'press': round(press) if press is not None else None,
            })

        _hourly_cache = result
        _hourly_cache_updated = now
        return result
    except Exception:
        return _hourly_cache or []
