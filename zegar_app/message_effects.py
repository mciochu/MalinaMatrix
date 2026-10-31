"""Validated message settings and frame rendering for the MAX7219 text studio."""
import math
import os

MESSAGE_EFFECTS = {
    "scroll_left": "Przewijanie w lewo",
    "scroll_right": "Przewijanie w prawo",
    "bounce": "Odbijanie od krawędzi",
    "static": "Tekst statyczny",
    "blink": "Miganie",
    "typewriter": "Litera po literze",
    "wave": "Fala",
    "drop": "Wjazd z góry",
}
MESSAGE_FONTS = ("CONFIGURED", "BUILTIN:LCD_FONT", "BUILTIN:TINY_FONT")
HORIZONTAL_ALIGNMENTS = ("left", "center", "right")
VERTICAL_ALIGNMENTS = ("top", "center", "bottom")
MAX_MESSAGE_LENGTH = 280


def available_message_fonts():
    """Return only bundled/custom application-relative BDF files and known built-ins."""
    from .fonts import list_available_fonts
    return list(MESSAGE_FONTS) + list_available_fonts()


def default_message_options(duration=10):
    return {
        "effect": "scroll_left",
        "speed": 35,
        "duration": max(1, min(600, int(duration))),
        "font": "CONFIGURED",
        "align": "center",
        "vertical": "center",
    }


def message_options_payload():
    fonts = []
    for font in available_message_fonts():
        if font == "CONFIGURED":
            label = "Font z konfiguracji zegara"
        elif font.startswith("BUILTIN:"):
            label = "LCD — wbudowany" if font.endswith("LCD_FONT") else "Tiny — wbudowany"
        else:
            label = os.path.basename(font)
        fonts.append({"id": font, "label": label})
    return {
        "effects": [{"id": key, "label": value} for key, value in MESSAGE_EFFECTS.items()],
        "fonts": fonts,
        "alignments": list(HORIZONTAL_ALIGNMENTS),
        "vertical_alignments": list(VERTICAL_ALIGNMENTS),
        "max_text_length": MAX_MESSAGE_LENGTH,
    }


def _bounded_integer(payload, key, default, minimum, maximum):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} musi być liczbą całkowitą")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} musi być w zakresie {minimum}–{maximum}")
    return value


def normalize_message_payload(payload, default_duration=10):
    """Validate and normalize a browser command before it reaches the display loop."""
    if not isinstance(payload, dict):
        raise ValueError("Oczekiwano obiektu JSON")
    raw_text = payload.get("text", "")
    if not isinstance(raw_text, str):
        raise ValueError("text musi być tekstem")
    clean_text = "".join(char if char >= " " or char == "\t" else " " for char in raw_text)
    clean_text = " ".join(clean_text.replace("\t", " ").split())
    if not clean_text:
        raise ValueError("Wpisz tekst do wyświetlenia")
    if len(clean_text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Tekst może mieć maksymalnie {MAX_MESSAGE_LENGTH} znaków")
    effect = str(payload.get("effect", "scroll_left")).strip().lower()
    if effect not in MESSAGE_EFFECTS:
        raise ValueError("Nieobsługiwany efekt animacji")
    speed = _bounded_integer(payload, "speed", 35, 1, 100)
    duration = _bounded_integer(payload, "duration", int(default_duration), 1, 600)
    font = payload.get("font", "CONFIGURED")
    if not isinstance(font, str) or font not in available_message_fonts():
        raise ValueError("Wybrany font nie jest dostępny w tej instalacji")
    align = str(payload.get("align", "center")).strip().lower()
    if align not in HORIZONTAL_ALIGNMENTS:
        raise ValueError("Nieprawidłowe wyrównanie poziome")
    vertical = str(payload.get("vertical", "center")).strip().lower()
    if vertical not in VERTICAL_ALIGNMENTS:
        raise ValueError("Nieprawidłowe wyrównanie pionowe")
    return {
        "text": clean_text, "effect": effect, "speed": speed, "duration": duration,
        "font": font, "align": align, "vertical": vertical,
    }


def _aligned_x(width, text_width, align):
    if align == "left":
        return 0
    if align == "right":
        return width - text_width
    return (width - text_width) // 2


def _aligned_y(height, text_height, align):
    if align == "top":
        return 0
    if align == "bottom":
        return height - text_height
    return (height - text_height) // 2


def draw_message_frame(draw, message, font, width, height, elapsed, options, draw_text, text_size):
    """Render one animation frame. Drawing functions are injected for hardware-free testing."""
    if not message:
        return
    effect = options.get("effect", "scroll_left")
    speed = max(1, min(100, int(options.get("speed", 35))))
    horizontal = options.get("align", "center")
    vertical = options.get("vertical", "center")
    text_width, text_height = text_size(message, font=font)
    base_y = max(0, min(height - text_height, _aligned_y(height, text_height, vertical)))
    speed_px = 4.0 + speed * 0.8
    seconds = max(0.0, float(elapsed))
    if effect == "scroll_left":
        span = width + text_width + 8
        x = width - int((seconds * speed_px) % max(1, span))
        draw_text(draw, (x, base_y), message, font=font, fill="white")
        return
    if effect == "scroll_right":
        span = width + text_width + 8
        x = -text_width + int((seconds * speed_px) % max(1, span))
        draw_text(draw, (x, base_y), message, font=font, fill="white")
        return
    if effect == "bounce":
        travel = abs(width - text_width)
        phase = (seconds * speed_px) % max(1.0, travel * 2.0)
        offset = phase if phase <= travel else travel * 2.0 - phase
        x = int(offset) if text_width <= width else -int(offset)
        draw_text(draw, (x, base_y), message, font=font, fill="white")
        return
    if effect == "blink":
        frequency = 0.5 + speed / 30.0
        if int(seconds * frequency * 2.0) % 2 == 0:
            x = _aligned_x(width, text_width, horizontal)
            draw_text(draw, (x, base_y), message, font=font, fill="white")
        return
    if effect == "typewriter":
        characters = min(len(message), int(seconds * (0.5 + speed * 0.2)))
        visible = message[:characters]
        if visible:
            visible_width = text_size(visible, font=font)[0]
            x = _aligned_x(width, visible_width, horizontal)
            draw_text(draw, (x, base_y), visible, font=font, fill="white")
        return
    if effect == "wave":
        x = _aligned_x(width, text_width, horizontal)
        phase = seconds * (0.8 + speed / 18.0)
        for index, character in enumerate(message):
            character_width = text_size(character, font=font)[0]
            y = max(0, min(height - text_height, base_y + int(round(math.sin(phase + index * 0.9) * 2))))
            draw_text(draw, (x, y), character, font=font, fill="white")
            x += character_width
        return
    if effect == "drop":
        x = _aligned_x(width, text_width, horizontal)
        fall_speed = 2.0 + speed * 0.55
        y = min(base_y, int(-text_height + seconds * fall_speed))
        draw_text(draw, (x, y), message, font=font, fill="white")
        return
    x = _aligned_x(width, text_width, horizontal)
    draw_text(draw, (x, base_y), message, font=font, fill="white")
