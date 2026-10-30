"""Example custom screen. Copy and edit this file to create another screen."""
SCREEN_ID = "example_status"
REQUIRES = ("sensors",)


def render(context):
    """Return 8 row bitmasks. Bit 0 is the leftmost pixel; bit 63 is the rightmost."""
    rows = [0] * 8
    temperature = context.get("sensors", {}).get("temp")
    if temperature is None:
        return rows
    # A compact level marker; replace this with your own 64x8 bitmap drawing logic.
    level = max(0, min(63, int(round(float(temperature) + 20))))
    for x in range(level + 1):
        rows[6] |= 1 << x
    rows[7] = 0x3F
    return rows
