"""HTTP endpoints for remote messages and display-test modes."""
import json
import sys
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from .config import get_settings
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

class MessageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
        if self.path == '/weather-style':
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
        global _pending_message, _pending_message_options, _message_received_time, _display_test_mode, _weather_display_style
        global _lamp_enabled, _lamp_brightness, _lamp_density
        if self.path == '/lamp':
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
