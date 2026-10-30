"""Bitmap-font loading helpers for the MAX7219 display."""
import os

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def list_available_fonts():
    """List bundled BDF fonts by application-relative path."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
    found = []
    for folder, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".bdf"):
                found.append(os.path.relpath(os.path.join(folder, filename), _APP_ROOT))
    return sorted(found)


class BDFLegacyFont:
    """BDF font exposed as vertical byte columns for luma.core.legacy."""

    def __init__(self, glyphs):
        self.glyphs = glyphs

    def __getitem__(self, code):
        # Unused/unsupported characters render as a small blank glyph.
        return self.glyphs.get(code, [0] * 4)


def load_bdf_legacy_font(path):
    """Load a BDF font and convert its glyphs to luma's legacy column format."""
    with open(path, "r", encoding="ascii") as font_file:
        lines = [line.strip() for line in font_file]

    ascent = 8
    for line in lines:
        if line.startswith("FONT_ASCENT "):
            ascent = int(line.split()[1])
            break

    glyphs = {}
    i = 0
    while i < len(lines):
        if not lines[i].startswith("STARTCHAR "):
            i += 1
            continue

        encoding = None
        advance = None
        bounding_box = None
        bitmap_rows = []
        in_bitmap = False
        i += 1

        while i < len(lines) and lines[i] != "ENDCHAR":
            line = lines[i]
            if line == "BITMAP":
                in_bitmap = True
            elif in_bitmap:
                bitmap_rows.append(line)
            elif line.startswith("ENCODING "):
                encoding = int(line.split()[1])
            elif line.startswith("DWIDTH "):
                advance = int(line.split()[1])
            elif line.startswith("BBX "):
                bounding_box = tuple(map(int, line.split()[1:5]))
            i += 1

        if encoding is not None and advance is not None and bounding_box is not None:
            width, height, x_offset, y_offset = bounding_box
            columns = [0] * max(1, advance)
            packed_width = ((width + 7) // 8) * 8
            top = ascent - (y_offset + height)

            for row_index, row_hex in enumerate(bitmap_rows[:height]):
                row_bits = int(row_hex, 16)
                y = top + row_index
                if not 0 <= y < 8:
                    continue
                for x_index in range(width):
                    x = x_offset + x_index
                    if 0 <= x < len(columns) and ((row_bits >> (packed_width - x_index - 1)) & 1):
                        columns[x] |= 1 << y

            glyphs[encoding] = columns
        i += 1

    required = set(map(ord, "0123456789:"))
    if not required.issubset(glyphs):
        raise ValueError("BDF font is missing clock digits or colon")
    return BDFLegacyFont(glyphs)
