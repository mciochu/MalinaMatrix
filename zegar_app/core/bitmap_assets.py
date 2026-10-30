"""Small monochrome bitmap loader for user-supplied 1-bit images."""
import json
import os
import re

_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,48}$")


def _asset_root():
    from ..config import get_settings
    settings = get_settings()
    return settings.resolve_path(settings.get("assets", "images_dir", "zegar_app/assets/images"))


def _rows_to_masks(rows, width):
    result = []
    for value in rows:
        if isinstance(value, str):
            if len(value) != width or any(char not in "01" for char in value):
                raise ValueError("Bitmap rows must contain width characters of 0 or 1")
            bits = sum((1 << index) for index, char in enumerate(value) if char == "1")
        elif isinstance(value, int) and not isinstance(value, bool) and 0 <= value < (1 << width):
            bits = value
        else:
            raise ValueError("Bitmap rows must be binary strings or valid integers")
        result.append(bits)
    return tuple(result)


def load_bitmap(name):
    """Load a JSON or plain PBM image without importing imaging libraries."""
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("Invalid bitmap name")
    root = _asset_root()
    json_path = os.path.join(root, name + ".json")
    pbm_path = os.path.join(root, name + ".pbm")
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError("Bitmap JSON must contain an object")
        width = int(data.get("width", 8))
        height = int(data.get("height", 8))
        rows = data.get("rows")
        if not 1 <= width <= 64 or height != 8 or not isinstance(rows, list) or len(rows) != 8:
            raise ValueError("Bitmap must define width 1..64, height 8 and exactly 8 rows")
        return _rows_to_masks(rows, width)

    if os.path.isfile(pbm_path):
        tokens = []
        with open(pbm_path, "r", encoding="ascii") as stream:
            for line in stream:
                line = line.split("#", 1)[0]
                tokens.extend(line.split())
        if len(tokens) < 3 or tokens[0] != "P1":
            raise ValueError("PBM image must use plain ASCII P1 format")
        width, height = int(tokens[1]), int(tokens[2])
        pixels = tokens[3:]
        if not 1 <= width <= 64 or height != 8 or len(pixels) != width * height:
            raise ValueError("PBM image must be 1..64 pixels wide and exactly 8 pixels high")
        if any(value not in ("0", "1") for value in pixels):
            raise ValueError("PBM pixels must be 0 or 1")
        rows = ["".join(pixels[y * width:(y + 1) * width]) for y in range(height)]
        return _rows_to_masks(rows, width)

    raise FileNotFoundError(f"No JSON or PBM bitmap named '{name}' in {root}")


def list_bitmaps():
    """List available JSON/PBM bitmaps without decoding their content."""
    root = _asset_root()
    try:
        names = set()
        for filename in os.listdir(root):
            stem, ext = os.path.splitext(filename)
            if ext.lower() in {".json", ".pbm"} and _NAME.fullmatch(stem):
                names.add(stem)
        return sorted(names)
    except OSError:
        return []


def draw_bitmap(draw, bitmap, x=0, y=0, fill="white"):
    """Draw an 8-row bitmap; bit zero is the leftmost pixel."""
    for row_index, mask in enumerate(bitmap):
        bit = 0
        while mask:
            if mask & 1:
                draw.point((x + bit, y + row_index), fill=fill)
            mask >>= 1
            bit += 1
