# LED Message Panel

The Malina Matrix browser dashboard includes a compact control for sending short messages to the Raspberry Pi MAX7219 display. It uses the existing Python display loop and does not start a second process or use a different display driver.

## Dashboard controls

The mobile-friendly panel intentionally exposes only three display modes:

- **Scroll left** — moves the full message from right to left and repeats during the selected duration.
- **Scroll right** — moves the full message from left to right and repeats during the selected duration.
- **Static text** — holds the message in one position.

The user enters up to 280 characters, selects one of four durations (10 seconds, 30 seconds, 1 minute or 5 minutes), and presses **Display message**. The **Stop** button cancels the message and restores the normal clock screen.

The browser interface does not expose the matrix preview, font selection, alignment, speed controls, or presets. Messages use the configured message font and centered alignment; scrolling uses a fixed default speed. This keeps the phone interface short and easy to use.

When the selected duration expires, the clock and normal screen schedule resume automatically.

## Rendering and compatibility

The Python renderer and HTTP API retain compatibility with the existing animation effects and message settings. The simplified dashboard offers only the three modes listed above; advanced effects are not presented as dashboard controls.

The physical display is eight pixels high. Rendering uses the existing MAX7219 path and does not use grayscale PWM or unsupported per-pixel brightness.

## HTTP API

The local control service listens on the configured web port (8088 by default).

- `GET /message-options` returns available effects, fonts and alignment options for compatible clients.
- `GET /message` returns the pending message and settings.
- `POST /message` accepts JSON with text, effect, speed, duration, font, align and vertical.
- `POST /message` with `{"stop": true}` cancels the message and restores the normal display cycle.
- The older `POST /send` plain-text endpoint remains supported and uses the default left-scroll effect.

Example request from the simplified dashboard:

~~~json
{
  "text": "MALINA MATRIX",
  "effect": "scroll_left",
  "speed": 35,
  "duration": 30
}
~~~

The API enforces a 280-character limit and validates message settings. As with the rest of the local control API, it has no authentication. Keep it on a trusted LAN and do not expose port 8088 directly to the internet.

## Raspberry Pi scope

The implementation uses the existing Python, luma.led_matrix and MAX7219 path. It adds no BeagleBone backend and does not change any BeagleBone configuration. The browser dashboard can run on a phone or computer; actual rendering runs on the Raspberry Pi attached to the matrix.
