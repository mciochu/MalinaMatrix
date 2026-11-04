"""Unit tests for selecting the remaining-day Open-Meteo precipitation forecast."""
import unittest

from zegar_app.weather import select_precipitation_forecast


class PrecipitationForecastTests(unittest.TestCase):
    def test_selects_highest_probability_from_remaining_hours(self):
        hourly = {
            "time": [
                "2026-11-04T08:00", "2026-11-04T14:00",
                "2026-11-04T17:00", "2026-11-04T20:00",
            ],
            "precipitation_probability": [95, 30, 75, 60],
            "weather_code": [61, 61, 71, 61],
            "rain": [1.0, 0.2, 0.0, 0.5],
            "snowfall": [0.0, 0.0, 0.5, 0.0],
        }
        result = select_precipitation_forecast(hourly, "2026-11-04T12:00")
        self.assertEqual(result, {
            "probability": 75.0, "kind": "snow", "time": "2026-11-04T17:00"
        })

    def test_probability_is_not_added_or_averaged(self):
        hourly = {
            "time": ["2026-11-04T13:00", "2026-11-04T15:00"],
            "precipitation_probability": [40, 55],
            "weather_code": [61, 61],
            "rain": [0.1, 0.2],
            "snowfall": [0, 0],
        }
        result = select_precipitation_forecast(hourly, "2026-11-04T12:00")
        self.assertEqual(result["probability"], 55.0)
        self.assertEqual(result["kind"], "rain")

    def test_ignores_hours_before_current_local_hour(self):
        hourly = {
            "time": ["2026-11-04T09:00", "2026-11-04T18:00"],
            "precipitation_probability": [100, 20],
            "weather_code": [71, 61],
            "rain": [0, 0.1],
            "snowfall": [1, 0],
        }
        result = select_precipitation_forecast(hourly, "2026-11-04T12:00")
        self.assertEqual(result["probability"], 20.0)
        self.assertEqual(result["kind"], "rain")

    def test_no_precipitation_returns_neutral_result(self):
        hourly = {
            "time": ["2026-11-04T12:00", "2026-11-04T18:00"],
            "precipitation_probability": [0, None],
            "weather_code": [1, 3],
            "rain": [0, 0],
            "snowfall": [0, 0],
        }
        self.assertEqual(
            select_precipitation_forecast(hourly, "2026-11-04T12:00"),
            {"probability": None, "kind": None, "time": None},
        )

    def test_snow_code_wins_even_if_snowfall_amount_is_zero(self):
        hourly = {
            "time": ["2026-11-04T19:00"],
            "precipitation_probability": [35],
            "weather_code": [73],
            "rain": [0],
            "snowfall": [0],
        }
        result = select_precipitation_forecast(hourly, "2026-11-04T12:00")
        self.assertEqual(result["kind"], "snow")
        self.assertEqual(result["probability"], 35.0)


if __name__ == "__main__":
    unittest.main()
