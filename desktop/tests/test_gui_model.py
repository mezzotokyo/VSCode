"""Headless unit tests for the desktop app's pure logic."""

from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parents[1]
if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

import errors  # noqa: E402
import gui_model  # noqa: E402
from gui_model import LaunchConditions  # noqa: E402


class PresetTests(unittest.TestCase):
    def test_presets_match_expected_values_and_labels(self) -> None:
        expected = (
            (0.47, "球体（既定値）"),
            (0.348, "MLB（無回転）"),
            (0.358, "MLB（2500rpm, 自由飛行）"),
            (0.3, "NPB"),
        )
        self.assertEqual(gui_model.DRAG_PRESETS, expected)

    def test_preset_label_known_and_unknown(self) -> None:
        self.assertEqual(gui_model.preset_label(0.47), "球体（既定値）（Cd=0.47）")
        self.assertEqual(gui_model.preset_label(0.3), "NPB（Cd=0.3）")
        self.assertEqual(gui_model.preset_label(0.5), "Cd=0.5")


class ValidateDtTests(unittest.TestCase):
    def test_accepts_default_and_bounds(self) -> None:
        self.assertIsNone(gui_model.validate_dt("0.01"))
        self.assertIsNone(gui_model.validate_dt("0.0001"))
        self.assertIsNone(gui_model.validate_dt("10"))

    def test_rejects_underflow(self) -> None:
        self.assertEqual(
            gui_model.validate_dt("0.00001"),
            "刻み幅 dt は 0.0001 以上で指定してください。",
        )

    def test_rejects_overflow(self) -> None:
        self.assertEqual(
            gui_model.validate_dt("11"),
            "刻み幅 dt は 10.0 以下で指定してください。",
        )

    def test_rejects_step_mismatch(self) -> None:
        self.assertEqual(
            gui_model.validate_dt("0.00015"),
            "刻み幅 dt は 0.0001 単位で指定してください。",
        )

    def test_rejects_non_numeric(self) -> None:
        message = "刻み幅 dt には数値を指定してください。"
        self.assertEqual(gui_model.validate_dt("abc"), message)
        self.assertEqual(gui_model.validate_dt(""), message)


class SimulateTests(unittest.TestCase):
    def test_reference_scenario_matches_spec(self) -> None:
        outcome = gui_model.simulate(LaunchConditions())
        result = outcome.result
        self.assertAlmostEqual(result.ideal_range, 213.60, delta=0.01)
        self.assertAlmostEqual(result.ground_range, 101.12, delta=0.01)
        self.assertAlmostEqual(result.flight_time, 4.37, delta=0.01)
        self.assertTrue(result.landed)
        self.assertFalse(result.timed_out)
        self.assertAlmostEqual(outcome.reduction_percent, 52.7, delta=0.1)

    def test_fixed_mode_timestep_is_constant(self) -> None:
        outcome = gui_model.simulate(LaunchConditions())
        self.assertAlmostEqual(outcome.result.timestep_min, 0.01)

    def test_adaptive_mode_shortens_timestep(self) -> None:
        outcome = gui_model.simulate(
            LaunchConditions(dt=5.0, adaptive=True)
        )
        self.assertTrue(outcome.result.landed)
        self.assertLess(outcome.result.timestep_min, 5.0)

    def test_drag_preset_changes_range(self) -> None:
        heavy = gui_model.simulate(LaunchConditions(drag_coefficient=0.47))
        light = gui_model.simulate(LaunchConditions(drag_coefficient=0.3))
        self.assertLess(heavy.result.ground_range, light.result.ground_range)

    def test_too_coarse_timestep_raises(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with self.assertRaises(gui_model.SimulationDiverged):
                gui_model.simulate(LaunchConditions(dt=100.0))


class FormattingTests(unittest.TestCase):
    def test_format_number(self) -> None:
        self.assertEqual(gui_model.format_number(101.1234), "101.12")
        self.assertEqual(gui_model.format_number(4.371, 1), "4.4")

    def test_format_decimal_trims_trailing_zeros(self) -> None:
        self.assertEqual(gui_model.format_decimal(0.01), "0.01")
        self.assertEqual(gui_model.format_decimal(0.0001), "0.0001")


class DownsampleTests(unittest.TestCase):
    def test_short_trajectory_is_unchanged(self) -> None:
        points = [gui_model.TrajectoryPoint(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]
        self.assertEqual(gui_model._downsample(points, 2000), points)

    def test_long_trajectory_keeps_last_point(self) -> None:
        points = [
            gui_model.TrajectoryPoint(float(i), float(i), 0.0, 0.0, 0.0, 0.0)
            for i in range(5000)
        ]
        sampled = gui_model._downsample(points, 2000)
        self.assertLessEqual(len(sampled), 2000 + 1)
        self.assertIs(sampled[-1], points[-1])


class ErrorLocalizationTests(unittest.TestCase):
    def test_too_coarse_message_is_translated(self) -> None:
        raw = (
            "timestep dt=100 is too coarse: an upward launch reached the ground "
            "within the first step. Reduce dt below 1.24049."
        )
        translated = errors.localize_error(raw)
        self.assertIn("dt=100", translated)
        self.assertIn("1.24049", translated)
        self.assertIn("粗すぎます", translated)

    def test_unknown_message_passes_through(self) -> None:
        self.assertEqual(errors.localize_error("boom"), "boom")


if __name__ == "__main__":
    unittest.main()
