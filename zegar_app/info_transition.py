"""Szybkie, opcjonalne przejście danych na matrycy 8x8."""
import time
from .config import get_settings

# Wyłączenie przywraca natychmiastowe przełączanie bez zmian w display.py.
INFO_TRANSITIONS_ENABLED = get_settings().boolean('modules', 'info_transitions', False)
TRANSITION_SECONDS = get_settings().number('effects', 'info_transition_seconds', 0.14, 0.01, 2.0)
BLANK_SECONDS = get_settings().number('effects', 'info_blank_seconds', 0.045, 0.0, 1.0)
FRAME_INTERVAL = get_settings().number('effects', 'info_frame_seconds', 0.025, 0.01, 1.0)


class InfoTransition:
    """Krótki błysk-wygaszenie tylko dla pola informacji, nie dla zegara/wykresu."""
    def __init__(self):
        self.current_key = None
        self.started_at = 0.0

    def update(self, key):
        if key != self.current_key:
            self.current_key = key
            self.started_at = time.monotonic()

    def active(self):
        return (INFO_TRANSITIONS_ENABLED and self.started_at > 0
                and time.monotonic() - self.started_at < TRANSITION_SECONDS)

    def visible(self):
        if not INFO_TRANSITIONS_ENABLED or not self.active():
            return True
        # Jedno krótkie wygaszenie, po którym nowa informacja pojawia się jasno.
        return time.monotonic() - self.started_at >= BLANK_SECONDS
