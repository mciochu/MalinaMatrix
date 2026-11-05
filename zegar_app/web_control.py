"""HTTP endpoints for remote messages and display-test modes."""
import json
import sys
import time
import os
import re
import tempfile
import configparser
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from http.server import HTTPServer, BaseHTTPRequestHandler
from .config import get_settings
from .history import get_history_range, get_latest_reading, HistoryRangeTooLarge
from .message_effects import default_message_options, message_options_payload, normalize_message_payload

_settings = get_settings()
_LAMP_MODULE_ENABLED = _settings.boolean("modules", "lamp", True)
_MESSAGES_MODULE_ENABLED = _settings.boolean("modules", "messages", True)

# --- SERWER HTTP DO ODBIERANIA WIADOMOŚCI Z PRZEGLĄDARKI ---
_pending_message = None
_pending_message_options = default_message_options(_settings.integer("web", "message_duration_seconds", 10, 1, 600))
_message_received_time = 0
_display_test_mode = None  # None = cykl automatyczny; temp/hum/press/weather/night = wymuszony test
_weather_display_style = _settings.get("weather", "display_style", "icon").lower()
# Tymczasowy podgląd/test planszy pogody sterowany z panelu WWW.
_weather_preview = {"enabled": False, "kind": None, "probability": 0}

if _weather_display_style not in {"icon", "letters"}:
    _weather_display_style = "icon"
# Tryb lampki jest chwilowym poleceniem WWW i po restarcie pozostaje wyłączony.
_lamp_enabled = False
_lamp_brightness = _settings.integer("brightness", "lamp_default_brightness", 100, 0, 100)
_lamp_density = _settings.integer("brightness", "lamp_default_density", 100, 0, 100)
_audio_status = {'connected': False, 'playing': False, 'device': None}
MESSAGE_DISPLAY_SECONDS = _settings.integer("web", "message_duration_seconds", 10, 1, 600)
WEB_HOST = _settings.get("web", "host", "0.0.0.0")
WEB_PORT = _settings.integer("web", "port", 8088, 1, 65535)

# Static localization resources are served through this existing API because
# the dashboard directory on some installations is intentionally read-only.
_WEB_ASSETS_DIR = Path(__file__).resolve().parent / "web"
if not _WEB_ASSETS_DIR.is_dir():
    _WEB_ASSETS_DIR = Path(__file__).resolve().parent.parent / "web"
_I18N_FILES = {
    "/i18n/config.json": _WEB_ASSETS_DIR / "config" / "languages.json",
    "/i18n/locales/pl.json": _WEB_ASSETS_DIR / "locales" / "pl.json",
    "/i18n/locales/en.json": _WEB_ASSETS_DIR / "locales" / "en.json",
}


_CONFIG_PATH = Path(_settings.path).resolve()
_CONFIG_LOCK = __import__("threading").RLock()
_LIVE_KEYS = {
 ("clock","format_24h"),("clock","show_seconds"),
 ("fonts","day"),("fonts","sensor"),("fonts","night"),("fonts","message"),("fonts","fallback"),("fonts","sensor_fallback"),
 ("display","screen_order"),("display","screen_dwell_seconds"),("display","normal_refresh_seconds"),("display","message_refresh_seconds"),("display","animation_refresh_seconds"),("display","night_mode_enabled"),("display","night_start_hour"),("display","night_end_hour"),
 ("brightness","day_contrast"),("brightness","night_contrast"),("history","log_interval_seconds"),("weather","display_style"),
 *{("layout",k) for k in ("weather_icon_x","weather_icon_y","temperature_x","temperature_y","precipitation_icon_x","precipitation_icon_y","precipitation_bar_x","precipitation_bar_y","graph_x","graph_y","info_value_x","info_value_y","wifi_x","wifi_y","clock_offset_x","clock_offset_y")}
}
_CONFIG_LABELS={"modules":"Moduły","hardware":"Sprzęt i matryca","clock":"Zegar","fonts":"Czcionki","display":"Ekrany i harmonogram","brightness":"Jasność","sensor":"Odczyt czujnika","sensors":"Sterowniki czujników","sensors.bme280":"Czujnik BME280","sensors.ds18b20":"Czujnik DS18B20","sensors.sht31":"Czujnik SHT31","sensors.dht22":"Czujnik DHT22","history":"Historia i baza danych","weather":"Pogoda","network":"Sieć","web":"Serwer WWW","screens":"Ekrany dodatkowe","extensions":"Rozszerzenia","effects":"Animacje i efekty","assets":"Zasoby"}
def _config_parser():
 p=configparser.ConfigParser(interpolation=None); p.optionxform=str.lower
 with _CONFIG_PATH.open("r",encoding="utf-8") as f:p.read_file(f)
 return p
def _config_kind(value):
 v=value.strip().lower()
 if v in ("true","false","yes","no","on","off"):return "boolean"
 if re.fullmatch(r"-?\d+",v):return "integer"
 if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)",v):return "number"
 return "text"
def _clock_layout_width(parser):
 # Use the same glyph advances as the configured BDF clock font so the
 # editor's selection box follows the real clock width (including seconds).
 show_seconds = parser.getboolean("clock", "show_seconds", fallback=False)
 sample = "00:00:00" if show_seconds else "00:00"
 spec = parser.get("fonts", "day", fallback="BUILTIN:LCD_FONT").strip()
 if spec.upper().startswith("BUILTIN:"):
  builtin = spec.split(":", 1)[1].upper()
  advance = 3 if builtin == "TINY_FONT" else 6
  return min(64, len(sample) * advance)
 font_path = Path(spec).expanduser()
 if not font_path.is_absolute():
  font_path = _CONFIG_PATH.parent / font_path
 if font_path.suffix.lower() != ".bdf" or not font_path.is_file():
  return min(64, len(sample) * 6)
 advances = {}
 try:
  lines = font_path.read_text(encoding="ascii").splitlines()
  i = 0
  while i < len(lines):
   if lines[i].startswith("STARTCHAR "):
    encoding = advance = None
    i += 1
    while i < len(lines) and lines[i] != "ENDCHAR":
     if lines[i].startswith("ENCODING "):
      encoding = int(lines[i].split()[1])
     elif lines[i].startswith("DWIDTH "):
      advance = int(lines[i].split()[1])
     i += 1
    if encoding is not None and advance is not None:
     advances[encoding] = max(1, advance)
   i += 1
  width = sum(advances.get(ord(char), 4) for char in sample)
  return max(1, min(64, width))
 except (OSError, UnicodeError, ValueError):
  return min(64, len(sample) * 6)


def _config_payload():
 p=_config_parser()
 definitions=[
  ("layout","Pozycje na matrycy",["layout"]),
  ("display","Wygląd i zegar",["display","brightness","clock","fonts"]),
  ("sensors","Czujniki i pogoda",["sensor","sensors","sensors.bme280","sensors.ds18b20","sensors.sht31","sensors.dht22","weather"]),
  ("features","Funkcje i dodatki",["modules","screens","extensions","effects","assets"]),
  ("system","Sprzęt i system",["hardware","history","network","web"]),
 ]
 labels={
  "weather_icon_x":"Ikona pogody · X","weather_icon_y":"Ikona pogody · Y",
  "temperature_x":"Temperatura · X","temperature_y":"Temperatura · Y",
  "precipitation_icon_x":"Ikona rodzaju opadów · X","precipitation_icon_y":"Ikona rodzaju opadów · Y",
  "precipitation_bar_x":"Pasek opadów · X","precipitation_bar_y":"Pasek opadów · Y",
  "graph_x":"Wykresy · X","graph_y":"Wykresy · Y",
  "info_value_x":"Wartość pomiaru · X","info_value_y":"Wartość pomiaru · Y",
  "wifi_x":"Wskaźnik Wi-Fi · X","wifi_y":"Wskaźnik Wi-Fi · Y",
  "clock_offset_x":"Przesunięcie zegara · X","clock_offset_y":"Przesunięcie zegara · Y",
 }
 groups=[]
 for gid,title,sections in definitions:
  fields=[]
  for section in sections:
   if not p.has_section(section):continue
   for key,value in p.items(section):
    kind=_config_kind(value); choices=["icon","letters"] if (section,key)==("weather","display_style") else None
    fields.append({"section":section,"key":key,"label":labels.get(key,key.replace("_"," ").capitalize()),"value":value,"kind":kind,"live":(section,key) in _LIVE_KEYS,"choices":choices})
  groups.append({"id":gid,"label":title,"fields":fields})
 return {"path":str(_CONFIG_PATH),"width":64,"height":8,"clock_width":_clock_layout_width(p),"groups":groups}
def _save_config_value(section,key,value):
 global _weather_display_style
 if not isinstance(section,str) or not isinstance(key,str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+",section) or not re.fullmatch(r"[a-zA-Z0-9_.-]+",key):raise ValueError("Nieprawidłowa nazwa ustawienia")
 if isinstance(value,(dict,list)) or value is None:raise ValueError("Nieprawidłowa wartość")
 text=str(value).strip()
 if len(text)>512 or "\n" in text or "\r" in text:raise ValueError("Wartość jest za długa lub zawiera niedozwolone znaki")
 with _CONFIG_LOCK:
  parser=_config_parser()
  if not parser.has_option(section,key):raise ValueError("Nieznane ustawienie")
  old=parser.get(section,key).strip(); kind=_config_kind(old)
  if kind=="boolean":
   if isinstance(value,bool):text="true" if value else "false"
   elif text.lower() in ("true","false","yes","no","on","off"):text="true" if text.lower() in ("true","yes","on") else "false"
   else:raise ValueError("Wymagana wartość tak/nie")
  elif kind=="integer":
   try:n=int(text)
   except ValueError:raise ValueError("Wymagana liczba całkowita")
   if abs(n)>1000000:raise ValueError("Liczba poza zakresem")
   text=str(n)
  elif kind=="number":
   try:n=float(text)
   except ValueError:raise ValueError("Wymagana liczba")
   if not __import__("math").isfinite(n) or abs(n)>1000000:raise ValueError("Liczba poza zakresem")
   text=str(n)
  if (section,key)==("weather","display_style") and text not in ("icon","letters"):raise ValueError("Dozwolone: icon lub letters")
  coordinate_limits={
   "weather_icon_x":(0,56),"weather_icon_y":(0,0),"temperature_x":(0,51),"temperature_y":(0,3),
   "precipitation_icon_x":(0,56),"precipitation_icon_y":(0,2),"precipitation_bar_x":(0,54),"precipitation_bar_y":(0,0),
   "graph_x":(0,46),"graph_y":(6,7),"info_value_x":(0,52),"info_value_y":(0,3),
   "wifi_x":(0,63),"wifi_y":(0,7),"clock_offset_x":(-63,63),"clock_offset_y":(-7,7)
  }
  if section=="layout" and key in coordinate_limits:
   low,high=coordinate_limits[key]
   try: coordinate=int(text)
   except ValueError: raise ValueError("Współrzędna musi być liczbą całkowitą")
   if not low<=coordinate<=high: raise ValueError(f"Dozwolony zakres: {low}–{high}")
   text=str(coordinate)
  if (section,key)==("display","screen_order"):
   allowed={"temperature","humidity","pressure","weather"}; items=[x.strip().lower() for x in text.split(",") if x.strip()]
   if not items or len(items)!=len(set(items)) or not set(items)<=allowed:raise ValueError("Nieprawidłowa kolejność ekranów")
   text=", ".join(items)
  if (section,key)==("sensors","enabled"):
   allowed={"bme280","ds18b20","sht31","dht22"}; items=[x.strip().lower() for x in text.split(",") if x.strip()]
   if not set(items)<=allowed:raise ValueError("Nieznany sterownik czujnika")
   text=", ".join(items)
  lines=_CONFIG_PATH.read_text(encoding="utf-8").splitlines(keepends=True); active=None; found=False
  for i,line in enumerate(lines):
   m=re.match(r"\s*\[([^]]+)\]",line)
   if m:active=m.group(1).strip().lower()
   if active==section.lower() and re.match(r"\s*"+re.escape(key)+r"\s*=",line,re.I):
    ending="\n" if line.endswith("\n") else ""; prefix=re.match(r"(\s*"+re.escape(key)+r"\s*=\s*)",line,re.I).group(1)
    raw=line.rstrip("\r\n"); tail=re.search(r"\s+[;#].*$",raw[len(prefix):]); comment=tail.group(0) if tail else ""
    lines[i]=prefix+text+comment+ending; found=True; break
  if not found:raise ValueError("Nie odnaleziono ustawienia w pliku")
  fd,tmp=tempfile.mkstemp(prefix=".zegar.conf.",dir=str(_CONFIG_PATH.parent),text=True)
  try:
   with os.fdopen(fd,"w",encoding="utf-8") as f:f.writelines(lines);f.flush();os.fsync(f.fileno())
   os.chmod(tmp,_CONFIG_PATH.stat().st_mode);os.replace(tmp,_CONFIG_PATH)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  _settings.reload_if_changed(force=True,min_interval=0.0)
  if (section,key)==("weather","display_style"):_weather_display_style=text
  return {"section":section,"key":key,"value":text,"live":(section,key) in _LIVE_KEYS}

_HISTORY_API_ERROR_LOCK = threading.Lock()
_HISTORY_API_LAST_ERROR = 0.0


class MessageHandler(BaseHTTPRequestHandler):
    def _send_json_response(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log_history_api_error(self, exc):
        global _HISTORY_API_LAST_ERROR
        now = time.monotonic()
        with _HISTORY_API_ERROR_LOCK:
            if now - _HISTORY_API_LAST_ERROR < 300.0:
                return
            _HISTORY_API_LAST_ERROR = now
        print(f"[HISTORY API] Read failed: {type(exc).__name__}", file=sys.stderr)

    def do_GET(self):
        request_path = urlsplit(self.path)
        if request_path.path == '/history':
            try:
                params = parse_qs(request_path.query, keep_blank_values=True)
                if set(params) - {'range'} or len(params.get('range', ['30d'])) != 1:
                    raise ValueError("Invalid history query")
                range_key = params.get('range', ['30d'])[0]
                payload = get_history_range(range_key)
                self._send_json_response(200, payload)
            except HistoryRangeTooLarge:
                self._send_json_response(413, {"error": "Requested history range is too large"})
            except ValueError:
                self._send_json_response(400, {"error": "Use one of: 24h, 3d, 7d, 30d"})
            except Exception as exc:
                self._log_history_api_error(exc)
                self._send_json_response(503, {"error": "History temporarily unavailable"})
            return

        if request_path.path == '/history/latest':
            if request_path.query:
                self._send_json_response(400, {"error": "This endpoint accepts no query parameters"})
                return
            try:
                latest = get_latest_reading()
                self._send_json_response(200, {"latest": latest})
            except Exception as exc:
                self._log_history_api_error(exc)
                self._send_json_response(503, {"error": "History temporarily unavailable"})
            return

        if self.path == '/config':
            try: body=json.dumps(_config_payload(),ensure_ascii=False).encode('utf-8'); status=200
            except Exception as exc: body=json.dumps({"error":str(exc)}).encode('utf-8'); status=500
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path in _I18N_FILES:
            try:
                body = _I18N_FILES[self.path].read_bytes()
            except OSError:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/weather-preview':
            body = json.dumps({"preview": _weather_preview}, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/weather-style':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_weather_display_style.encode('ascii'))
        elif self.path == '/lamp':
            body = json.dumps({'enabled': bool(_lamp_enabled and _LAMP_MODULE_ENABLED), 'brightness': _lamp_brightness,
                               'density': _lamp_density}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/message-options':
            body = json.dumps(message_options_payload(), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/message':
            body = json.dumps({
                'text': _pending_message or '',
                'options': _pending_message_options,
                'active': bool(_pending_message and time.time() - _message_received_time < _pending_message_options.get('duration', MESSAGE_DISPLAY_SECONDS))
            }, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/audio':
            body = json.dumps(_audio_status).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/config':
            try:
                length=int(self.headers.get('Content-Length',0))
                if length<1 or length>4096:raise ValueError("Nieprawidłowy rozmiar żądania")
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload,dict):raise ValueError("Oczekiwano obiektu JSON")
                result=_save_config_value(payload.get('section'),payload.get('key'),payload.get('value'))
                body=json.dumps({"ok":True,**result},ensure_ascii=False).encode('utf-8'); status=200
            except Exception as exc:
                body=json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False).encode('utf-8'); status=400
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        global _pending_message, _pending_message_options, _message_received_time, _display_test_mode, _weather_display_style
        global _lamp_enabled, _lamp_brightness, _lamp_density, _weather_preview, _display_test_mode
        if self.path == '/weather-preview':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length < 1 or content_length > 1024:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('Expected JSON object')
                enabled = payload.get('enabled', _weather_preview['enabled'])
                kind = payload.get('kind', _weather_preview.get('kind'))
                probability = payload.get('probability', _weather_preview.get('probability', 0))
                if not isinstance(enabled, bool):
                    raise ValueError('enabled must be boolean')
                if kind not in {'live', 'none', 'rain', 'snow'}:
                    raise ValueError('Invalid precipitation kind')
                if isinstance(probability, bool) or not isinstance(probability, int) or not 0 <= probability <= 100:
                    raise ValueError('probability must be an integer from 0 to 100')
                if kind == 'live':
                    kind, probability = None, None
                elif kind == 'none':
                    kind, probability = None, 0
                _weather_preview = {'enabled': enabled, 'kind': kind, 'probability': probability}
                if enabled:
                    _display_test_mode = 'weather'
                elif _display_test_mode == 'weather':
                    _display_test_mode = None
                body = json.dumps({'preview': _weather_preview}, ensure_ascii=False).encode('utf-8')
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(str(exc).encode('utf-8'))
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/lamp':
            if not _LAMP_MODULE_ENABLED:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length < 1 or content_length > 256:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('Expected JSON object')
                enabled = payload.get('enabled', _lamp_enabled)
                brightness = payload.get('brightness', _lamp_brightness)
                density = payload.get('density', _lamp_density)
                if not isinstance(enabled, bool):
                    raise ValueError('enabled must be boolean')
                if isinstance(brightness, bool) or not isinstance(brightness, int) or not 0 <= brightness <= 100:
                    raise ValueError('brightness must be an integer from 0 to 100')
                if isinstance(density, bool) or not isinstance(density, int) or not 0 <= density <= 100:
                    raise ValueError('density must be an integer from 0 to 100')
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(str(exc).encode('utf-8'))
                return
            _lamp_enabled, _lamp_brightness, _lamp_density = enabled, brightness, density
            body = json.dumps({'enabled': _lamp_enabled, 'brightness': _lamp_brightness,
                               'density': _lamp_density}).encode('utf-8')
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/weather-style':
            content_length = min(int(self.headers.get('Content-Length', 0)), 32)
            requested = self.rfile.read(content_length).decode('utf-8').strip().lower()
            if requested not in {'letters', 'icon'}:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'Expected letters or icon')
                return
            _weather_display_style = requested
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_weather_display_style.encode('ascii'))
        elif self.path == '/message':
            if not _MESSAGES_MODULE_ENABLED:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length < 1 or content_length > 8192:
                    raise ValueError('Nieprawidłowy rozmiar żądania')
                payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('Oczekiwano obiektu JSON')
                if payload.get('stop') is True:
                    _pending_message = None
                    _message_received_time = 0
                    result = {'active': False, 'stopped': True}
                else:
                    normalized = normalize_message_payload(payload, MESSAGE_DISPLAY_SECONDS)
                    _pending_message = normalized.pop('text')
                    _pending_message_options = normalized
                    _message_received_time = time.time()
                    result = {'active': True, 'text': _pending_message, 'options': _pending_message_options}
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8'))
                return
            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/send':
            if not _MESSAGES_MODULE_ENABLED:
                self.send_response(404)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length < 1 or content_length > 8192:
                    raise ValueError('Invalid request size')
                body = self.rfile.read(content_length).decode('utf-8')
                normalized = normalize_message_payload({'text': body}, MESSAGE_DISPLAY_SECONDS)
                _pending_message = normalized.pop('text')
                _pending_message_options = normalized
                _message_received_time = time.time()
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(str(exc).encode('utf-8'))
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path == '/display-test':
            content_length = min(int(self.headers.get('Content-Length', 0)), 32)
            requested = self.rfile.read(content_length).decode('utf-8').strip().lower()
            allowed_modes = {'temp', 'hum', 'press', 'weather', 'night'}
            if requested == 'off':
                _display_test_mode = None
            elif requested in allowed_modes:
                _display_test_mode = requested
            else:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'Expected temp, hum, press, weather, night or off')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(('OFF' if _display_test_mode is None else _display_test_mode).encode('ascii'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass  # wycisz logi HTTP

def start_http_server():
    try:
        server = HTTPServer((WEB_HOST, WEB_PORT), MessageHandler)
        server.serve_forever()
    except Exception as e:
        print(f"HTTP server error on {WEB_HOST}:{WEB_PORT}: {e}", file=sys.stderr)

[executed on device: malina (5f975671-b674-4ac4-965e-55c199641524)]