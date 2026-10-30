"""Opcjonalna animacja opadających cyfr dziennego zegara."""
import time
from .config import get_settings

# Wyłącz tę funkcję bez zmian w pozostałej aplikacji: ustaw False.
FLIP_CLOCK_ENABLED = get_settings().boolean('modules', 'flip_clock', False)
ANIMATION_SECONDS = get_settings().number('effects', 'flip_seconds', 0.020, 0.005, 2.0)
FRAME_INTERVAL = get_settings().number('effects', 'flip_frame_seconds', 0.020, 0.01, 1.0)
DIGIT_HEIGHT = 8


class FlipClockAnimator:
    """Animuje wyłącznie zmienione znaki; pozostałe cyfry pozostają nieruchome."""
    def __init__(self, initial_text=""):
        self.current_text = initial_text
        self.previous_text = initial_text
        self.started_at = 0.0

    def update(self, new_text):
        if new_text != self.current_text:
            self.previous_text = self.current_text
            self.current_text = new_text
            self.started_at = time.monotonic()

    def active(self):
        return (FLIP_CLOCK_ENABLED and self.previous_text != self.current_text
                and time.monotonic() - self.started_at < ANIMATION_SECONDS)

    def draw(self, draw, xy, text_fn, textsize_fn, font, fill="white"):
        x0, y0 = xy
        if (not FLIP_CLOCK_ENABLED or not self.active()
                or len(self.previous_text) != len(self.current_text)):
            text_fn(draw, xy, self.current_text, font=font, fill=fill)
            return

        progress = min(1.0, max(0.0,
            (time.monotonic() - self.started_at) / ANIMATION_SECONDS))
        # Dwie fazy jak w zegarze klapkowym: stara cyfra opada,
        # po czym nowa wsuwa się z góry. Przy 8 pikselach wysokości
        # rozdzielenie faz daje czytelniejszy efekt niż nakładanie cyfr.
        split = 0.52
        for index, new_char in enumerate(self.current_text):
            old_char = self.previous_text[index]
            prefix = self.current_text[:index]
            char_x = x0 + textsize_fn(prefix, font=font)[0]
            if old_char == new_char:
                text_fn(draw, (char_x, y0), new_char, font=font, fill=fill)
                continue

            if progress < split:
                phase = progress / split
                eased = phase * phase * (3.0 - 2.0 * phase)
                offset = int(round(DIGIT_HEIGHT * eased))
                text_fn(draw, (char_x, y0 + offset), old_char,
                        font=font, fill=fill)
            else:
                phase = (progress - split) / (1.0 - split)
                eased = phase * phase * (3.0 - 2.0 * phase)
                offset = int(round(DIGIT_HEIGHT * (1.0 - eased)))
                text_fn(draw, (char_x, y0 - offset), new_char,
                        font=font, fill=fill)
