"""Hardware-independent tests for the Malina Matrix core."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from zegar_app.config import Settings
from zegar_app.core.bitmap_assets import load_bitmap, list_bitmaps
from zegar_app.core.screen_registry import ScreenRegistry
from zegar_app.sensor_hub import SensorHub
from zegar_app.message_effects import draw_message_frame, normalize_message_payload, MESSAGE_EFFECTS


class ConfigTests(unittest.TestCase):
    def test_typed_values_and_safe_fallbacks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.conf"
            path.write_text(
                "[display]\nscreen_dwell_seconds = 8.5\nnight_mode_enabled = yes\n"
                "bad_value = nan\n",
                encoding="utf-8",
            )
            settings = Settings(str(path))
            self.assertEqual(settings.number("display", "screen_dwell_seconds", 5.0, 0.5, 60), 8.5)
            self.assertTrue(settings.boolean("display", "night_mode_enabled", False))
            self.assertEqual(settings.number("display", "bad_value", 5.0, 0.5, 60), 5.0)

    def test_live_reload_keeps_previous_snapshot_until_valid_file_is_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.conf"
            path.write_text("[display]\nscreen_dwell_seconds = 5\n", encoding="utf-8")
            settings = Settings(str(path))
            self.assertEqual(settings.number("display", "screen_dwell_seconds", 1), 5.0)

            path.write_text("[display]\nscreen_dwell_seconds = 9\n", encoding="utf-8")
            os.utime(path, None)
            self.assertTrue(settings.reload_if_changed(force=True, min_interval=0.0))
            self.assertEqual(settings.number("display", "screen_dwell_seconds", 1), 9.0)

            path.write_text("[display\nscreen_dwell_seconds = 3\n", encoding="utf-8")
            os.utime(path, None)
            self.assertFalse(settings.reload_if_changed(force=True, min_interval=0.0))
            self.assertEqual(settings.number("display", "screen_dwell_seconds", 1), 9.0)


class AssetTests(unittest.TestCase):
    def test_example_bitmap_is_valid(self):
        bitmap = load_bitmap("example_signal")
        self.assertEqual(len(bitmap), 8)
        self.assertTrue(any(bitmap))
        self.assertIn("example_signal", list_bitmaps())


class ExtensionTests(unittest.TestCase):
    def test_sensor_plugin_runs_on_background_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sensor.conf"
            path.write_text(
                "[sensors]\nenabled = template\n[sensor]\nrefresh_seconds = 0.25\n",
                encoding="utf-8",
            )
            hub = SensorHub(Settings(str(path)))
            try:
                hub.start()
                deadline = time.monotonic() + 2.0
                values = {}
                while time.monotonic() < deadline:
                    values = hub.snapshot()
                    if values.get("temp") == 21.5:
                        break
                    time.sleep(0.02)
                self.assertEqual(values.get("temp"), 21.5)
            finally:
                hub.close()

    def test_custom_screen_returns_validated_bitmap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.conf"
            path.write_text(
                "[screens]\nplugins = example_status\n"
                "plugin_refresh_seconds = 0.25\nplugin_stale_seconds = 2\n",
                encoding="utf-8",
            )
            registry = ScreenRegistry(
                Settings(str(path)),
                {"sensors": True, "weather": True},
            )
            try:
                modes = registry.resolve_order(["example_status"])
                self.assertEqual(len(modes), 1)
                self.assertGreaterEqual(modes[0], 1000)
                frame = None
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    frame = registry.request_custom_frame(
                        modes[0],
                        {"sensors": {"temp": 22.5}, "width": 64, "height": 8},
                    )
                    if frame is not None:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(frame)
                self.assertEqual(len(frame), 8)
                self.assertEqual(frame[7], 0x3F)
            finally:
                registry.close()


if __name__ == "__main__":
    unittest.main()


class MessageStudioTests(unittest.TestCase):
    def test_message_options_are_normalized_and_bounded(self):
        result = normalize_message_payload({
            "text": "  Witaj   Malino  ", "effect": "wave", "speed": 72,
            "duration": 30, "align": "right", "vertical": "bottom", "font": "CONFIGURED",
        })
        self.assertEqual(result["text"], "Witaj Malino")
        self.assertEqual(result["effect"], "wave")
        self.assertEqual(result["speed"], 72)
        self.assertEqual(result["duration"], 30)
        self.assertEqual(result["align"], "right")
        self.assertEqual(result["vertical"], "bottom")

    def test_message_validation_rejects_invalid_settings(self):
        invalid_payloads = [
            {"text": "   "}, {"text": "test", "effect": "not-an-effect"},
            {"text": "test", "speed": 101}, {"text": "test", "duration": 0},
            {"text": "test", "font": "../../etc/passwd"}, {"text": "test", "align": "diagonal"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    normalize_message_payload(payload)

    def test_each_effect_renders_a_frame_without_hardware(self):
        calls = []
        def fake_draw(draw, position, value, **kwargs):
            calls.append((position, value))
        def fake_size(value, font=None):
            return (len(value) * 5, 7)
        for effect in MESSAGE_EFFECTS:
            with self.subTest(effect=effect):
                calls.clear()
                options = normalize_message_payload({
                    "text": "MALINA", "effect": effect, "speed": 50,
                    "duration": 10, "font": "CONFIGURED",
                })
                draw_message_frame(object(), options["text"], object(), 64, 8, 0.1,
                                   options, fake_draw, fake_size)
                self.assertTrue(calls, f"{effect} should draw at least one glyph")

    def test_scroll_speed_changes_message_position(self):
        calls = []
        def fake_draw(draw, position, value, **kwargs):
            calls.append(position)
        def fake_size(value, font=None):
            return (len(value) * 5, 7)
        options = normalize_message_payload({"text": "HELLO", "effect": "scroll_left", "speed": 30})
        draw_message_frame(object(), "HELLO", object(), 64, 8, 1.0, options, fake_draw, fake_size)
        first_x = calls[-1][0]
        calls.clear()
        draw_message_frame(object(), "HELLO", object(), 64, 8, 2.0, options, fake_draw, fake_size)
        self.assertNotEqual(first_x, calls[-1][0])
