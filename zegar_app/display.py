"""MAX7219 setup, screen scheduling, rendering, and display loop."""
import os
import signal
import sys
import threading
import time

from luma.core.interface.serial import spi, noop
from luma.led_matrix.device import max7219
from luma.core.render import canvas
from luma.core.legacy import text, textsize
from luma.core.legacy.font import proportional, LCD_FONT, TINY_FONT

from .fonts import load_bdf_legacy_font, list_available_fonts
from .config import get_settings
from .history import init_db, export_json_for_web, log_to_db, get_hourly_averages
from .network import check_internet
from .system_utils import is_time_synced
from .weather import weather_label, get_weather_nonblocking
from . import web_control
from .flip_clock import FlipClockAnimator, FLIP_CLOCK_ENABLED, FRAME_INTERVAL
from .info_transition import InfoTransition, INFO_TRANSITIONS_ENABLED, FRAME_INTERVAL as INFO_FRAME_INTERVAL
from .assets.icons.weather_icons import LED8x8ICONS as _WEATHER_ICONS
from .core.module_manager import ModuleManager
from .core.screen_registry import ScreenRegistry
from .sensor_hub import SensorHub


def _weather_icon_name(code):
    if code in (0, 1): return "SUNNY"
    if code in (2, 3): return "CLOUD"
    if code in (45, 48): return "UNKNOWN"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67): return "RAIN"
    if code in (71, 73, 75, 77, 85, 86): return "SNOW"
    if code in (80, 81, 82): return "SHOWERS"
    if code in (95, 96, 99): return "STORM"
    return "UNKNOWN"


def _draw_weather_icon(draw, x, y, code):
    """Narysuj ikonę LED 8x8 w obszarze planszy pogody."""
    icon = _WEATHER_ICONS.get(_weather_icon_name(code))
    if icon is None: return False
    for py in range(8):
        row = (icon >> (8 * py)) & 0xFF
        for px in range(8):
            if (row >> px) & 1:
                draw.point((x + px, y + py), fill="white")
    return True

def is_night():
    """Return whether the configured night schedule is currently active."""
    settings = get_settings()
    if not settings.boolean("display", "night_mode_enabled", True):
        return False
    hour = time.localtime().tm_hour
    start = settings.integer("display", "night_start_hour", 23, 0, 23)
    end = settings.integer("display", "night_end_hour", 6, 0, 23)
    if start == end:
        return False
    return hour >= start or hour < end if start > end else start <= hour < end


def _load_configured_font(spec, fallback_spec, description, verbose):
    """Ładuje BDF lub wbudowany font luma; przy błędzie używa bezpiecznego fallbacku."""
    builtins = {
        "LCD_FONT": proportional(LCD_FONT),
        "TINY_FONT": proportional(TINY_FONT),
    }
    def load_one(value):
        value = str(value).strip()
        if value.upper().startswith("BUILTIN:"):
            name = value.split(":", 1)[1].strip().upper()
            if name not in builtins:
                raise ValueError(f"nieznany font wbudowany: {name}")
            return builtins[name]
        path = get_settings().resolve_path(value)
        if not path.lower().endswith(".bdf"):
            raise ValueError("Use a .bdf file or BUILTIN:LCD_FONT / BUILTIN:TINY_FONT")
        if not os.path.isfile(path) and not os.path.isabs(value):
            matches = [item for item in list_available_fonts()
                       if os.path.basename(item).lower() == os.path.basename(value).lower()]
            if len(matches) == 1:
                path = get_settings().resolve_path(matches[0])
            elif len(matches) > 1:
                raise ValueError(f"font name '{value}' is ambiguous; use its full relative path")
        return load_bdf_legacy_font(path)
    try:
        result = load_one(spec)
        if verbose:
            print(f"[CONFIG] Font {description}: {spec}", file=sys.stderr)
        return result
    except Exception as exc:
        if verbose:
            print(f"[CONFIG] Nie można załadować fontu {description} ({spec}): {exc}", file=sys.stderr)
    try:
        return load_one(fallback_spec)
    except Exception:
        return proportional(LCD_FONT)


_BAYER_8X8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


def draw_lamp_pattern(draw, width, height, density):
    """Rysuj białe pole z regulowaną, stabilną gęstością punktów LED."""
    lit_threshold = max(0, min(64, int(round(float(density) * 64.0 / 100.0))))
    if lit_threshold <= 0:
        return
    if lit_threshold >= 64:
        draw.rectangle((0, 0, width - 1, height - 1), fill="white")
        return
    for y in range(height):
        row = _BAYER_8X8[y & 7]
        for x in range(width):
            if row[x & 7] < lit_threshold:
                draw.point((x, y), fill="white")


def run_clock(n, block_orientation, rotate, inreverse, show_seconds, blink=True, fmt24=True,
              i2c_addr=0x76, i2c_port=1, verbose=True, show_temp_only=False):
    settings = get_settings()
    modules = {
        "sensors": settings.boolean("modules", "sensors", True),
        "history": settings.boolean("modules", "history", True),
        "graph": settings.boolean("modules", "graph", True),
        "weather": settings.boolean("modules", "weather", True),
        "wifi_indicator": settings.boolean("modules", "wifi_indicator", True),
        "web_control": settings.boolean("modules", "web_control", True),
        "messages": settings.boolean("modules", "messages", True),
        "lamp": settings.boolean("modules", "lamp", True),
        "audio_visualizer": settings.boolean("modules", "audio_visualizer", False),
        "flip_clock": settings.boolean("modules", "flip_clock", False),
        "info_transitions": settings.boolean("modules", "info_transitions", False),
    }
    history_enabled = modules["history"]
    graph_enabled = modules["graph"] and history_enabled and modules["sensors"]
    day_contrast = settings.integer("brightness", "day_contrast", 1, 0, 255)
    night_contrast = settings.integer("brightness", "night_contrast", 0, 0, 255)
    NIGHT_CONTRAST = night_contrast
    # Zmierz etap programu po załadowaniu modułów; najpierw uruchom matrycę.
    startup_started = time.monotonic()
    stage_started = time.monotonic()
    spi_deadline = stage_started + 120.0
    last_spi_wait_log = -5.0
    while True:
        try:
            serial = spi(port=0, device=0, gpio=noop())
            break
        except Exception as exc:
            elapsed = time.monotonic() - stage_started
            if time.monotonic() >= spi_deadline:
                raise
            if elapsed - last_spi_wait_log >= 5.0:
                print(f"[STARTUP] waiting for usable SPI device ({elapsed:.1f}s): {exc}", file=sys.stderr)
                last_spi_wait_log = elapsed
            time.sleep(0.25)
    print(f"[STARTUP] SPI ready after {time.monotonic() - stage_started:.2f}s", file=sys.stderr)

    stage_started = time.monotonic()
    device = max7219(serial, cascaded=n or 1, block_orientation=block_orientation,
                     rotate=rotate or 0, blocks_arranged_in_reverse_order=inreverse)
    device.contrast(day_contrast)
    print(f"[STARTUP] MAX7219 initialized in {time.monotonic() - stage_started:.2f}s", file=sys.stderr)

    # Fonty można wymieniać w zegar.conf bez edycji kodu.
    fallback_font = settings.get("fonts", "fallback", "BUILTIN:LCD_FONT")
    time_font = _load_configured_font(
        settings.get("fonts", "day", "zegar_app/assets/fonts/8-series/MatrixChunky8X.bdf"),
        fallback_font, "godziny dziennej", verbose)
    sensor_font = _load_configured_font(
        settings.get("fonts", "sensor", "zegar_app/assets/fonts/6-series/MatrixChunky6.bdf"),
        settings.get("fonts", "sensor_fallback", "BUILTIN:TINY_FONT"),
        "wartości czujników", verbose)
    temp_font = _load_configured_font(
        settings.get("fonts", "night", "BUILTIN:TINY_FONT"),
        "BUILTIN:TINY_FONT", "zegara nocnego", verbose)
    clock_font = _load_configured_font(
        settings.get("fonts", "message", "BUILTIN:LCD_FONT"),
        fallback_font, "wiadomości", verbose)

    # Najpierw pokaż godzinę. Baza i NTP nie mogą blokować pierwszej klatki.
    now = time.localtime()
    if show_seconds:
        initial_clock_display = time.strftime('%H:%M:%S' if fmt24 else '%I:%M:%S', now)
    else:
        initial_clock_display = time.strftime('%H:%M' if fmt24 else '%I:%M', now)

    initial_night = is_night()
    if initial_night:
        device.contrast(night_contrast)
        initial_width = textsize(initial_clock_display, font=temp_font)[0]
        initial_x = (device.width - initial_width) // 2
        initial_y = (device.height - 5) // 2
        with canvas(device) as draw:
            text(draw, (initial_x, initial_y), initial_clock_display, font=temp_font, fill="white")
    else:
        device.contrast(day_contrast)
        with canvas(device) as draw:
            text(draw, (0, max(0, device.height - 8)), initial_clock_display, font=time_font, fill="white")

    print(f"[STARTUP] first clock frame rendered {time.monotonic() - startup_started:.2f}s after run_clock entry", file=sys.stderr)

    # Historia działa w tle; przy wyłączeniu nie otwieramy SQLite ani nie eksportujemy JSON.
    history_ready = threading.Event()
    if history_enabled:
        def prepare_history():
            stage_started = time.monotonic()
            init_db()
            print(f"[STARTUP] database initialized in {time.monotonic() - stage_started:.2f}s", file=sys.stderr)
            if settings.boolean("history", "export_on_start", True):
                stage_started = time.monotonic()
                export_json_for_web()
                print(f"[STARTUP] history exported in {time.monotonic() - stage_started:.2f}s", file=sys.stderr)
            history_ready.set()
        threading.Thread(target=prepare_history, daemon=True, name="history-init").start()
    else:
        history_ready.set()
        if verbose:
            print("[CONFIG] Historia wyłączona — SQLite nie jest uruchamiane.", file=sys.stderr)
    last_db_log = 0
    flip_clock = FlipClockAnimator(initial_clock_display)
    info_transition = InfoTransition()
    previous_info_mode = None

    def runtime_log(message):
        print(f"[EXTENSION] {message}", file=sys.stderr)

    # Core services use one coordinator; optional modules are imported only on demand.
    sensor_hub = SensorHub(settings, runtime_log) if modules["sensors"] else None
    if sensor_hub is not None:
        sensor_hub.start()

    if modules["web_control"]:
        http_thread = threading.Thread(target=web_control.start_http_server, daemon=True, name="web-control")
        http_thread.start()
        if verbose:
            print("[CONFIG] HTTP server started", file=sys.stderr)

    audio_setting = os.environ.get("AUDIO_VISUALIZER_ENABLED")
    if audio_setting is not None:
        modules["audio_visualizer"] = audio_setting.strip().lower() in ("1", "true", "yes", "on")
    module_manager = ModuleManager(modules, settings, runtime_log)
    module_manager.register("audio_visualizer", "zegar_app.audio_visualizer", "BluetoothAudioVisualizer")
    audio_visualizer = module_manager.get("audio_visualizer")
    module_manager.load_extensions(settings.list("extensions", "modules", ()))

    screen_registry = ScreenRegistry(settings, modules, runtime_log)
    requested_screens = settings.list(
        "display", "screen_order",
        ("temperature", "humidity", "pressure", "weather"))
    screen_modes = screen_registry.resolve_order(requested_screens)
    mode = screen_modes[0] if screen_modes else 0
    mode_started_at = time.monotonic()
    auto_cycle_active = False

    screen_dwell_seconds = settings.number("display", "screen_dwell_seconds", 5.0, 0.5, 3600.0)
    history_log_interval = settings.integer("history", "log_interval_seconds", 300, 30, 86400)
    normal_sleep = settings.number("display", "normal_refresh_seconds", 1.0, 0.02, 10.0)
    message_sleep = settings.number("display", "message_refresh_seconds", 0.05, 0.02, 2.0)
    animation_sleep = settings.number("display", "animation_refresh_seconds", 0.02, 0.01, 1.0)
    env_data = {}
    was_night = None
    last_contrast = None
    humidity_scale_mode = 0

    def restart_signature():
        restart_sections = ("modules", "hardware", "sensors", "web", "network",
                            "effects", "screens", "extensions")
        values = [(section, tuple(sorted(settings.items(section).items()))) for section in restart_sections]
        for section in settings.parser.sections():
            if section.startswith("sensors."):
                values.append((section, tuple(sorted(settings.items(section).items()))))
        values.extend([
            ("weather_source", settings.get("weather", "latitude", "50.98"),
             settings.get("weather", "longitude", "21.24"),
             settings.get("weather", "cache_seconds", "1800"),
             settings.get("weather", "retry_seconds", "300"),
             settings.get("weather", "request_timeout_seconds", "5")),
            ("history_paths", settings.get("history", "database_path", "/home/mciochu/sensor_data.db"),
             settings.get("history", "web_directory", "/var/www/html"),
             settings.get("history", "export_on_start", "true")),
        ])
        return tuple(values)

    active_restart_signature = restart_signature()
    font_signature = tuple(settings.get("fonts", key, default) for key, default in (
        ("day", "zegar_app/assets/fonts/8-series/MatrixChunky8X.bdf"),
        ("sensor", "zegar_app/assets/fonts/6-series/MatrixChunky6.bdf"),
        ("night", "BUILTIN:TINY_FONT"),
        ("message", "BUILTIN:LCD_FONT"),
        ("fallback", "BUILTIN:LCD_FONT"),
        ("sensor_fallback", "BUILTIN:TINY_FONT"),
    ))
    next_config_check = time.monotonic() + 2.0
    clock_format_24h = settings.boolean("clock", "format_24h", fmt24)
    clock_show_seconds = settings.boolean("clock", "show_seconds", show_seconds)

    def _handle_sigterm(signum, frame):
        raise KeyboardInterrupt

    try:
        previous_sigterm_handler = signal.signal(signal.SIGTERM, _handle_sigterm)
    except ValueError:
        previous_sigterm_handler = None

    try:
        while True:
            mode_changed_this_loop = False
            config_now = time.monotonic()
            if config_now >= next_config_check:
                next_config_check = config_now + 2.0
                if settings.reload_if_changed():
                    new_restart_signature = restart_signature()
                    if new_restart_signature != active_restart_signature:
                        print("[CONFIG] Some changes require a service restart; current module and hardware state is unchanged.", file=sys.stderr)
                        active_restart_signature = new_restart_signature

                    new_font_signature = tuple(settings.get("fonts", key, default) for key, default in (
                        ("day", "zegar_app/assets/fonts/8-series/MatrixChunky8X.bdf"),
                        ("sensor", "zegar_app/assets/fonts/6-series/MatrixChunky6.bdf"),
                        ("night", "BUILTIN:TINY_FONT"),
                        ("message", "BUILTIN:LCD_FONT"),
                        ("fallback", "BUILTIN:LCD_FONT"),
                        ("sensor_fallback", "BUILTIN:TINY_FONT"),
                    ))
                    if new_font_signature != font_signature:
                        fallback = settings.get("fonts", "fallback", "BUILTIN:LCD_FONT")
                        time_font = _load_configured_font(new_font_signature[0], fallback, "day clock", verbose)
                        sensor_font = _load_configured_font(new_font_signature[1], new_font_signature[5], "sensor values", verbose)
                        temp_font = _load_configured_font(new_font_signature[2], "BUILTIN:TINY_FONT", "night clock", verbose)
                        clock_font = _load_configured_font(new_font_signature[3], fallback, "messages", verbose)
                        font_signature = new_font_signature
                        print("[CONFIG] Font settings applied live.", file=sys.stderr)

                    day_contrast = settings.integer("brightness", "day_contrast", 1, 0, 255)
                    night_contrast = settings.integer("brightness", "night_contrast", 0, 0, 255)
                    NIGHT_CONTRAST = night_contrast
                    screen_dwell_seconds = settings.number("display", "screen_dwell_seconds", 5.0, 0.5, 3600.0)
                    normal_sleep = settings.number("display", "normal_refresh_seconds", 1.0, 0.02, 10.0)
                    message_sleep = settings.number("display", "message_refresh_seconds", 0.05, 0.02, 2.0)
                    animation_sleep = settings.number("display", "animation_refresh_seconds", 0.02, 0.01, 1.0)
                    history_log_interval = settings.integer("history", "log_interval_seconds", 300, 30, 86400)
                    requested_screens = settings.list("display", "screen_order",
                                                      ("temperature", "humidity", "pressure", "weather"))
                    new_screen_modes = screen_registry.resolve_order(requested_screens)
                    if new_screen_modes:
                        screen_modes = new_screen_modes
                        if mode not in screen_modes:
                            mode = screen_modes[0]
                            mode_changed_this_loop = True
                        mode_started_at = time.monotonic()
                    clock_format_24h = settings.boolean("clock", "format_24h", clock_format_24h)
                    clock_show_seconds = settings.boolean("clock", "show_seconds", clock_show_seconds)
                    fmt24 = clock_format_24h
                    show_seconds = clock_show_seconds
                    weather_style = settings.get("weather", "display_style", "icon").lower()
                    if weather_style in {"icon", "letters"}:
                        web_control._weather_display_style = weather_style
            # Check whether a message is currently active.
            msg_elapsed = time.time() - web_control._message_received_time
            is_showing_message = bool(modules["messages"] and modules["web_control"] and web_control._pending_message and msg_elapsed < web_control.MESSAGE_DISPLAY_SECONDS)

            lamp_active = bool(modules["lamp"] and modules["web_control"] and web_control._lamp_enabled)
            if audio_visualizer is not None:
                audio_active, audio_connected, audio_levels, audio_device = audio_visualizer.snapshot()
            else:
                audio_active, audio_connected, audio_levels, audio_device = False, False, (), None
            web_control._audio_status = {'enabled': audio_visualizer is not None, 'connected': bool(audio_connected), 'playing': bool(audio_active), 'device': audio_device}
            audio_active = audio_active and not lamp_active
            actual_night = is_night()
            # Test pozwala wymusić tryb dzienny lub nocny niezależnie od godziny.
            night = (web_control._display_test_mode == 'night') if web_control._display_test_mode is not None else actual_night

            # Lampka korzysta z tego samego sterownika SPI, bez drugiego procesu.
            # MAX7219 ma 16 poziomów jasności; panel WWW ustawia je w procentach.
            if lamp_active:
                target_contrast = int(round(web_control._lamp_brightness * 15.0 / 100.0)) * 17
            else:
                target_contrast = NIGHT_CONTRAST if night else day_contrast
            if target_contrast != last_contrast:
                device.contrast(target_contrast)
                last_contrast = target_contrast
            was_night = night

            if not is_showing_message and not lamp_active:
                now = time.localtime()
                if show_seconds:
                    clock_display = time.strftime('%H:%M:%S' if fmt24 else '%I:%M:%S', now)
                else:
                    clock_display = time.strftime('%H:%M' if fmt24 else '%I:%M', now)
                if not night and FLIP_CLOCK_ENABLED:
                    flip_clock.update(clock_display)

            if not is_showing_message and not lamp_active and not audio_active:
                # Read cached sensor values only; hardware polling never blocks the display loop.
                env_data = sensor_hub.snapshot() if sensor_hub is not None else {}

                # Persist readings only while both sensor and history modules are enabled.
                current_time = time.time()
                if history_enabled and modules["sensors"] and current_time - last_db_log >= history_log_interval:
                    if not history_ready.is_set():
                        # Historia nadal przygotowuje się w tle; ponów próbę za sekundę.
                        last_db_log = current_time - 299
                    elif is_time_synced():
                        temp = env_data.get('temp')
                        hum = env_data.get('hum')
                        press = env_data.get('press')
                        if temp is not None or hum is not None or press is not None:
                            def persist_reading(sample_temp=temp, sample_hum=hum, sample_press=press):
                                log_to_db(sample_temp, sample_hum, sample_press)
                                export_json_for_web()

                            # Zapis historii nie może blokować odświeżania godziny.
                            threading.Thread(
                                target=persist_reading,
                                daemon=True,
                                name="sensor-persist"
                            ).start()
                        last_db_log = current_time
                    else:
                        if verbose:
                            print("Pominięto zapis do bazy - brak synchronizacji czasu; zegar działa dalej.", file=sys.stderr)
                        # Ponów próbę za około 60 sekund, bez wywoływania oczekiwania blokującego pętlę.
                        last_db_log = current_time - 240

            if not is_showing_message and not night and not lamp_active and not audio_active:
                # ----- TYLKO DZIEŃ: harmonogram ekranów -----
                if web_control._display_test_mode is None:
                    scheduler_now = time.monotonic()
                    if not auto_cycle_active:
                        # Po wiadomości/trybie nocnym licz pełny czas od ponownego
                        # narysowania bieżącej informacji.
                        auto_cycle_active = True
                        mode_changed_this_loop = True
                    elif scheduler_now - mode_started_at >= screen_dwell_seconds:
                        if screen_modes:
                            try:
                                current_index = screen_modes.index(mode)
                            except ValueError:
                                current_index = -1
                            mode = screen_modes[(current_index + 1) % len(screen_modes)]
                            mode_changed_this_loop = True
                else:
                    # Tryby testowe pozostają przypięte, nie uczestniczą w cyklu.
                    auto_cycle_active = False
                    requested_mode = {'temp': 0, 'hum': 1, 'press': 2, 'weather': 3}[web_control._display_test_mode]
                    if requested_mode in screen_modes:
                        mode = requested_mode
            else:
                # Wiadomość/tryb nocny nie powinny zużywać czasu ekspozycji ekranu.
                auto_cycle_active = False

            if not is_showing_message and not night and not lamp_active and not audio_active:
                # ----- TYLKO DZIEŃ: przygotowanie napisów na wyświetlacz -----
                if mode >= 1000:
                    info_display = "__CUSTOM_SCREEN__"
                elif mode == 0:
                    val = env_data.get('temp')
                    info_display = "{:.1f}C".format(val) if val is not None else ""
                elif mode == 1:
                    val = env_data.get('hum')
                    info_display = "{:.0f}%".format(val) if val is not None else ""
                elif mode == 2:
                    val = env_data.get('press')
                    info_display = "{:.0f}hP".format(val) if val is not None else ""
                else:
                    info_display = "__POGODA__"

                # Animuj wyłącznie zmianę pola informacji. Godzina i wykres pozostają niezależne.
                if mode == 3 and modules["weather"]:
                    weather_now = get_weather_nonblocking()
                    info_key = (mode, weather_now.get('code'), weather_now.get('temp_min'), weather_now.get('temp_max'))
                else:
                    info_key = (mode, info_display)
                info_transition.update(info_key)
                previous_info_mode = mode

                if verbose:
                    print(f"Env data: {env_data} Mode: {mode}", file=sys.stderr)

            with canvas(device) as draw:
                if lamp_active:
                    # Lampka ma pierwszeństwo przed zegarem, planszami i wiadomościami.
                    draw_lamp_pattern(draw, device.width, device.height, web_control._lamp_density)
                elif is_showing_message:
                    # Przewijanie tekstu fontem LCD, płynna animacja
                    msg_width = textsize(web_control._pending_message, font=clock_font)[0]
                    total_scroll = msg_width + device.width
                    progress = msg_elapsed / web_control.MESSAGE_DISPLAY_SECONDS
                    x_offset = int(device.width - progress * total_scroll)
                    text(draw, (x_offset, 0), web_control._pending_message, font=clock_font, fill="white")
                elif audio_active:
                    # 32 pasma na 64 piksele: wąskie, dwupikselowe słupki
                    # pokazują więcej szczegółów rytmu i barwy dźwięku.
                    for band, level in enumerate(audio_levels):
                        # Perceptual height mapping: low-amplitude music must
                        # occupy several LED rows, not disappear into 1-pixel bars.
                        height = 0 if level < 0.008 else max(1, min(8, int(round((level ** 0.42) * 8.0))))
                        left = band * 2
                        for x in range(left, left + 2):
                            for row in range(height):
                                draw.point((x, 7 - row), fill="white")
                elif night:
                    # ----- TRYB NOCNY: tylko godzina na środku -----
                    tw = textsize(clock_display, font=temp_font)[0]
                    tx = (device.width - tw) // 2
                    ty = (device.height - 5) // 2  # TINY_FONT ~4-5px, wyśrodkuj w pionie
                    text(draw, (tx, ty), clock_display, font=temp_font, fill="white")
                else:
                    # ----- TRYB DZIENNY: zegar + wykres + dane -----
                    flip_clock.draw(draw, (0, max(0, device.height - 8)), text, textsize, time_font, fill="white") if FLIP_CLOCK_ENABLED else text(draw, (0, max(0, device.height - 8)), clock_display, font=time_font, fill="white")

                    if info_transition.visible():
                        if info_display == "__POGODA__" and modules["weather"]:
                            # Pogoda: skrót + min/max temperatura
                            w = get_weather_nonblocking()
                            if w['temp_max'] is not None:
                                tmin = "{:.0f}".format(w['temp_min']) if w['temp_min'] is not None else "--"
                                tmax = "{:.0f}".format(w['temp_max']) if w['temp_max'] is not None else "--"
                                label = weather_label(w['code'])
                                if web_control._weather_display_style == 'icon':
                                    if _draw_weather_icon(draw, 24, 0, w['code']):
                                        text(draw, (38, 2), tmin + "/" + tmax, font=temp_font, fill="white")
                                    else:
                                        text(draw, (24, 2), label, font=temp_font, fill="white")
                                        text(draw, (43, 2), tmin + "/" + tmax, font=temp_font, fill="white")
                                else:
                                    text(draw, (24, 2), label + " " + tmin + "/" + tmax, font=temp_font, fill="white")
                        elif info_display:
                            value_x = device.width - 23 if mode == 2 else device.width - 22
                            text(draw, (value_x, 3), info_display, font=sensor_font, fill="white")

                    # Wykres 6h — ten sam obszar: x=26..43, podstawa y=7.
                    # Puste przedziały pozostają puste, aby historia nie przesuwała się w bok.
                    if mode in (0, 1, 2) and graph_enabled:
                        graph_hours = settings.integer("history", "graph_hours", 6, 1, 168)
                        hourly = get_hourly_averages(graph_hours)
                        if len(hourly) >= 2:
                            metric_key = 'temp' if mode == 0 else ('hum' if mode == 1 else 'press')
                            live_key = 'temp' if mode == 0 else ('hum' if mode == 1 else 'press')
                            slots = [entry.get(metric_key) for entry in hourly[:18]]

                            # Ostatni słupek wilgotności pokazuje bieżący odczyt bez
                            # mieszania go z historią, dzięki czemu zmiana o 1% nie ginie.
                            # Dla temperatury i ciśnienia pozostaje dotychczasowe łagodne mieszanie.
                            live_value = env_data.get(live_key) if isinstance(env_data, dict) else None
                            if slots and live_value is not None:
                                try:
                                    live_value = float(live_value)
                                    previous = slots[-1]
                                    if mode == 1:
                                        slots[-1] = live_value
                                    else:
                                        slots[-1] = live_value if previous is None else (0.25 * float(previous) + 0.75 * live_value)
                                except (TypeError, ValueError):
                                    pass

                            # Wilgotność: wygładzaj historię, ale nigdy bieżący odczyt.
                            raw_slots = slots[:]
                            if mode == 1:
                                for i, value in enumerate(raw_slots):
                                    if value is None or i == len(raw_slots) - 1:
                                        continue
                                    weighted = [(float(value), 0.6)]
                                    if i > 0 and raw_slots[i - 1] is not None:
                                        weighted.append((float(raw_slots[i - 1]), 0.2))
                                    if i + 1 < len(raw_slots) and raw_slots[i + 1] is not None:
                                        weighted.append((float(raw_slots[i + 1]), 0.2))
                                    weight_sum = sum(weight for _, weight in weighted)
                                    slots[i] = sum(sample * weight for sample, weight in weighted) / weight_sum

                            valid_values = [float(v) for v in slots if v is not None]
                            if len(valid_values) >= 2:
                                v_min, v_max = min(valid_values), max(valid_values)
                                spread = v_max - v_min
                                bar_w = 1
                                bar_gap = 0
                                bar_start_x = 20
                                baseline_y = 7

                                if mode == 1:
                                    # Adaptacja bazuje na ostatnich sześciu próbkach (~2 h), nie całej historii.
                                    recent_values = [float(v) for v in raw_slots[-6:] if v is not None]
                                    if not recent_values:
                                        recent_values = valid_values[-6:]
                                    recent_spread = max(recent_values) - min(recent_values)

                                    # Cztery zakresy z histerezą: małe zmiany pozostają powiększone,
                                    # a większe wahania automatycznie przełączają wykres na szerszą skalę.
                                    if humidity_scale_mode == 0:
                                        if recent_spread >= 18:
                                            humidity_scale_mode = 3
                                        elif recent_spread >= 9:
                                            humidity_scale_mode = 2
                                        elif recent_spread >= 4:
                                            humidity_scale_mode = 1
                                    elif humidity_scale_mode == 1:
                                        if recent_spread >= 18:
                                            humidity_scale_mode = 3
                                        elif recent_spread >= 9:
                                            humidity_scale_mode = 2
                                        elif recent_spread <= 2.5:
                                            humidity_scale_mode = 0
                                    elif humidity_scale_mode == 2:
                                        if recent_spread >= 18:
                                            humidity_scale_mode = 3
                                        elif recent_spread <= 2.5:
                                            humidity_scale_mode = 0
                                        elif recent_spread <= 6:
                                            humidity_scale_mode = 1
                                    else:
                                        if recent_spread <= 2.5:
                                            humidity_scale_mode = 0
                                        elif recent_spread <= 6:
                                            humidity_scale_mode = 1
                                        elif recent_spread <= 14:
                                            humidity_scale_mode = 2

                                    # Tryby: czuły 6 pp, średni 12 pp, szeroki 24 pp, bardzo szeroki 40 pp.
                                    spans = (6.0, 12.0, 24.0, 40.0)
                                    humidity_span = max(spans[humidity_scale_mode], recent_spread * 1.25)
                                    sorted_recent = sorted(recent_values)
                                    middle = len(sorted_recent) // 2
                                    if len(sorted_recent) % 2:
                                        humidity_center = sorted_recent[middle]
                                    else:
                                        humidity_center = (sorted_recent[middle - 1] + sorted_recent[middle]) / 2.0
                                    humidity_center = float(round(humidity_center))
                                    humidity_min = humidity_center - humidity_span / 2.0

                                    # Słupki wilgotności — 18 kolumn x=20..37, podstawa y=7.
                                    # Adaptacyjna skala zmienia czułość, ale styl pozostaje słupkowy.
                                    humidity_heights = []
                                    for value in slots[:18]:
                                        if value is None:
                                            humidity_heights.append(None)
                                            continue
                                        normalized = min(1.0, max(0.0, (float(value) - humidity_min) / humidity_span))
                                        height = max(1, min(7, int(round(normalized * 6)) + 1))
                                        humidity_heights.append(height)

                                    # Jeśli zaokrąglenie ukryłoby zmianę ostatniego odczytu,
                                    # odchyl wysokość ostatniego słupka o 1 piksel w kierunku zmiany.
                                    # Dzięki temu 1% nie ginie nawet w trybie szerokiej skali.
                                    if humidity_heights and humidity_heights[-1] is not None and slots[-1] is not None:
                                        previous_value = next((float(v) for v in reversed(slots[:-1]) if v is not None), None)
                                        previous_height = next((h for h in reversed(humidity_heights[:-1]) if h is not None), None)
                                        if previous_value is not None and previous_height is not None:
                                            current_value = float(slots[-1])
                                            current_height = humidity_heights[-1]
                                            if current_value > previous_value and current_height <= previous_height:
                                                humidity_heights[-1] = min(7, previous_height + 1)
                                            elif current_value < previous_value and current_height >= previous_height:
                                                humidity_heights[-1] = max(1, previous_height - 1)

                                    for i, height in enumerate(humidity_heights):
                                        if height is None:
                                            continue
                                        x = bar_start_x + i * (bar_w + bar_gap)
                                        for row in range(height):
                                            draw.point((x, baseline_y - row), fill="white")
                                else:
                                    # Temperatura i ciśnienie zachowują dotychczasową formę słupków.
                                    for i, value in enumerate(slots):
                                        if value is None:
                                            continue
                                        x = bar_start_x + i * (bar_w + bar_gap)
                                        if spread < 0.05:
                                            h = 3
                                        else:
                                            normalized = min(1.0, max(0.0, (float(value) - v_min) / spread))
                                            h = max(1, min(7, int((normalized ** 0.78) * 7)))
                                        for row in range(h):
                                            draw.point((x, baseline_y - row), fill="white")

                # Custom screens render to an 8-row buffer on their own worker.
                # The main display loop only copies the latest validated bitmap.
                if mode >= 1000 and not lamp_active and not is_showing_message:
                    draw.rectangle((0, 0, device.width - 1, device.height - 1), fill="black")
                    frame = screen_registry.request_custom_frame(mode, {
                        "width": device.width,
                        "height": device.height,
                        "clock": clock_display,
                        "sensors": dict(env_data),
                        "timestamp": time.time(),
                        "local_time": time.localtime(),
                    })
                    if frame is not None:
                        for y, row_mask in enumerate(frame):
                            for x in range(min(device.width, 64)):
                                if row_mask & (1 << x):
                                    draw.point((x, y), fill="white")
                    else:
                        # Keep a useful fallback visible while a custom screen starts or recovers.
                        text(draw, (0, max(0, device.height - 8)), clock_display,
                             font=time_font, fill="white")

                # Wi-Fi indicator is optional and only shown in day mode.
                if modules["wifi_indicator"] and not night and not audio_active:
                    has_internet = check_internet()
                    wx, wy = device.width - 1, 0
                    if has_internet:
                        draw.point((wx, wy), fill="white")
                    elif (time.time() % 2.0) < 0.3:
                        draw.point((wx, wy), fill="white")

            # Start ekspozycji licz po faktycznym narysowaniu nowego ekranu.
            if mode_changed_this_loop:
                mode_started_at = time.monotonic()

            # Zwykle odświeżaj co sekundę, ale przy zbliżającej się zmianie
            # skróć oczekiwanie, by nie dodawać kolejnej pełnej sekundy opóźnienia.
            sleep_seconds = animation_sleep if (lamp_active or audio_active) else (message_sleep if is_showing_message else (min(FRAME_INTERVAL if (not night and FLIP_CLOCK_ENABLED and flip_clock.active()) else normal_sleep, INFO_FRAME_INTERVAL) if (not night and INFO_TRANSITIONS_ENABLED and info_transition.active()) else (FRAME_INTERVAL if (not night and FLIP_CLOCK_ENABLED and flip_clock.active()) else normal_sleep)))
            if (auto_cycle_active and web_control._display_test_mode is None and
                    not night and not is_showing_message and not lamp_active):
                remaining = screen_dwell_seconds - (time.monotonic() - mode_started_at)
                if remaining <= 0:
                    sleep_seconds = 0.02
                else:
                    sleep_seconds = min(sleep_seconds, remaining)
            time.sleep(max(0.02, sleep_seconds))
    except KeyboardInterrupt:
        device.show()
        device.clear()
    finally:
        if sensor_hub is not None:
            sensor_hub.close()
        screen_registry.close()
        module_manager.close()
        if previous_sigterm_handler is not None:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)
