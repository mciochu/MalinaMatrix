# LED Message Studio

The Malina Matrix browser dashboard includes an editor for animated text on the Raspberry Pi MAX7219 display. It targets the 64×8 matrix in the reference build and uses the existing Python display loop; it does not start a second process or use a different display driver.

## Controls

- Text: up to 280 characters. Line breaks are converted to spaces because the reference display is one row of eight pixels.
- Effect: eight hardware-rendered animation modes.
- Speed: 1–100. The value controls pixel travel speed, typing rate, wave rate or blink frequency, depending on the effect.
- Duration: 1–600 seconds. When it expires, the clock and normal screen schedule resume automatically.
- Font: the message font from the clock configuration, built-in Luma fonts, or bundled/custom BDF fonts found under zegar_app/assets/fonts/.
- Alignment: horizontal left/center/right and vertical top/center/bottom.
- Preview: a browser-side 64×8 approximation of motion and timing; exact glyph pixels depend on the selected BDF file and actual MAX7219 module.
- Presets: up to 30 complete settings saved in the current browser local storage. Presets are not synchronized between devices.

## Effects

| Effect | Behaviour |
|---|---|
| Scroll left | Moves the full message right-to-left and repeats during the duration. |
| Scroll right | Moves the full message left-to-right and repeats during the duration. |
| Bounce | Moves the message between horizontal bounds. |
| Static | Holds the message at the selected alignment. |
| Blink | Alternates visible and blank frames. |
| Typewriter | Reveals characters progressively at the selected rate. |
| Wave | Moves each glyph vertically with a phase offset. |
| Drop | Moves the message down from above the display and then holds it. |

The physical display is only eight pixels high. Effects are designed around that limitation; they do not simulate colour, grayscale PWM or unsupported per-pixel brightness.

## HTTP API

The local control service listens on the configured web port (8088 by default).

- GET /message-options returns effect names, font choices and alignment options.
- GET /message returns the pending message and settings.
- POST /message accepts JSON with text, effect, speed, duration, font, align and vertical.
- POST /message with {"stop": true} cancels the message and restores the normal display cycle.
- The older POST /send plain-text endpoint remains supported and uses the default left-scroll effect.

Example JSON:

~~~json
{
  "text": "MALINA MATRIX",
  "effect": "wave",
  "speed": 45,
  "duration": 15,
  "font": "CONFIGURED",
  "align": "center",
  "vertical": "center"
}
~~~

The API enforces a 280-character limit and only accepts known fonts from the project or built-in font identifiers. As with the rest of the local control API, it has no authentication. Keep it on a trusted LAN and do not expose port 8088 directly to the internet.

## Raspberry Pi scope

The implementation uses the existing Python, luma.led_matrix and MAX7219 path. It adds no BeagleBone backend and does not change any BeagleBone configuration. The browser preview can run on a phone or computer; actual rendering runs on the Raspberry Pi attached to the matrix.
