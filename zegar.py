#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kompatybilny punkt wejścia dla modularnego zegara MAX7219.

Usługa systemd nadal uruchamia /home/mciochu/zegar.py.
Implementacja znajduje się w pakiecie zegar_app.
"""

# Zachowaj publiczne importy starego monolitycznego modułu, aby nie zmieniać
# istniejących narzędzi i poleceń diagnostycznych korzystających z tych funkcji.
from zegar_app.fonts import BDFLegacyFont, load_bdf_legacy_font
from zegar_app.system_utils import is_time_synced, force_time_sync, wait_for_time_sync
from zegar_app.network import check_internet
from zegar_app import web_control
from zegar_app.web_control import MessageHandler, start_http_server, MESSAGE_DISPLAY_SECONDS
from zegar_app.history import (
    DB_PATH,
    WEB_DIR,
    init_db,
    log_to_db,
    export_json_for_web,
    get_hourly_averages,
)
from zegar_app.weather import weather_label, get_weather, get_weather_nonblocking
from zegar_app.sensors import TemperatureReader
from zegar_app.display import is_night, run_clock
from zegar_app.main import main


def __getattr__(name):
    # Zachowaj dynamiczny odczyt zmiennych stanu, których wartości aktualizuje
    # handler HTTP w module web_control.
    if name in {"_pending_message", "_message_received_time", "_display_test_mode"}:
        return getattr(web_control, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
