"""Headless unit tests for the desktop N-body window's pure logic.

The Tk widgets (:mod:`nbody_app`, :class:`trajectory_chart.NBodyChart`) are
exercised by launching the app; everything they depend on lives in
``gui_model`` / ``trajectory_chart`` and is tested here without a display.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parents[1]
if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

import errors  # noqa: E402
import gui_model  # noqa: E402
import trajectory_chart  # noqa: E402
from gui_model import NBodyConditions, NBodySpec  # noqa: E402

CIRCULAR_STATE = (1.0e6, 0.0, 0.0, 0.0, 1.0e3, 0.0)


def spec(
    name: str = "天体1",
    density: float = 1000.0,
    radius: float = 1.0,
    state=CIRCULAR_STATE,
) -> NBodySpec:
    return NBodySpec(name=name, density=density, radius=radius, state=state)


class PresetTests(unittest.TestCase):
    def test_preset_values_and_labels(self) -> None:
        self.assertEqual(
            gui_model.NBODY_PRESETS,
            (
                ("earth_moon", "地球–月（2天体）"),
                ("earth_moon_satellite", "地球–月＋人工衛星（3天体）"),
            ),
        )

    def test_earth_moon_is_circular_about_the_barycentre(self) -> None:
        bodies = gui_model.nbody_preset_bodies("earth_moon")
        self.assertEqual([body.name for body in bodies], ["地球", "月"])
        for body in bodies:
            self.assertGreater(body.mu, 0.0)
        # The centre of mass sits at the origin: opposite sides, mu-weighted.
        earth, moon = bodies
        self.assertAlmostEqual(
            earth.state[0], -moon.state[0] * moon.mu / earth.mu, delta=1e-6
        )
        self.assertLess(earth.state[0], 0.0)
        self.assertGreater(moon.state[0], 0.0)
        # Both bodies orbit (non-zero velocities in opposite directions).
        self.assertNotEqual(earth.state[4], 0.0)
        self.assertNotEqual(moon.state[4], 0.0)
        self.assertLess(earth.state[4] * moon.state[4], 0.0)

    def test_satellite_preset_adds_a_circular_low_orbit(self) -> None:
        bodies = gui_model.nbody_preset_bodies("earth_moon_satellite")
        self.assertEqual(len(bodies), 3)
        earth, _moon, satellite = bodies
        separation = math.dist(earth.state[:3], satellite.state[:3])
        expected = gui_model.NBODY_EARTH_RADIUS + gui_model.NBODY_SATELLITE_ALTITUDE
        self.assertAlmostEqual(separation, expected, delta=1.0)

    def test_preset_conditions_validate_and_stay_within_the_step_budget(self) -> None:
        for value, _label in gui_model.NBODY_PRESETS:
            with self.subTest(preset=value):
                conditions = gui_model.nbody_preset_conditions(value)
                self.assertIsNone(gui_model.validate_nbody_conditions(conditions))
                self.assertLessEqual(
                    conditions.estimated_steps, gui_model.MAX_NBODY_STEPS
                )

    def test_earth_moon_preset_covers_one_period(self) -> None:
        conditions = gui_model.nbody_preset_conditions("earth_moon")
        period_days = conditions.max_time / 86400.0
        self.assertAlmostEqual(period_days, 27.3, delta=0.1)
        self.assertEqual(conditions.dt, 60.0)

    def test_satellite_preset_six_hours_at_fine_timestep(self) -> None:
        conditions = gui_model.nbody_preset_conditions("earth_moon_satellite")
        self.assertEqual(conditions.dt, 5.0)
        self.assertEqual(conditions.max_time, 6 * 3600.0)

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(ValueError):
            gui_model.nbody_preset_bodies("unknown")
        with self.assertRaises(ValueError):
            gui_model.nbody_preset_conditions("unknown")


class BodyCatalogTests(unittest.TestCase):
    # Measured GM values (m^3/s^2) used only to check the derived mu stays
    # close; the catalogue itself stores density and radius.
    MEASURED_MU = {
        "太陽": 1.327_124_400_18e20,
        "水星": 2.203_2e13,
        "金星": 3.248_585_92e14,
        "地球": 3.986_004_418e14,
        "月": 4.904_869_5e12,
        "火星": 4.282_837e13,
        "木星": 1.266_865_34e17,
        "土星": 3.793_118_7e16,
        "天王星": 5.793_939e15,
        "海王星": 6.836_529e15,
    }

    def test_catalog_is_the_sun_planets_and_moon(self) -> None:
        names = [name for name, _d, _r in gui_model.NBODY_CATALOG]
        self.assertEqual(
            names,
            ["太陽", "水星", "金星", "地球", "月", "火星", "木星", "土星", "天王星", "海王星"],
        )
        self.assertEqual(len(names), len(set(names)))

    def test_catalog_entries_are_positive(self) -> None:
        for name, density, radius in gui_model.NBODY_CATALOG:
            with self.subTest(body=name):
                self.assertGreater(density, 0.0)
                self.assertGreater(radius, 0.0)

    def test_derived_mu_matches_measured_values_closely(self) -> None:
        # Volume-mean density is an approximation; the GUI accepts a small
        # error against measured GM (see the module docstring in gui_model).
        for name, density, radius in gui_model.NBODY_CATALOG:
            with self.subTest(body=name):
                mu = gui_model.nbody_mu(density, radius)
                expected = self.MEASURED_MU[name]
                self.assertLess(abs(mu - expected) / expected, 0.005)

    def test_mu_formula(self) -> None:
        expected = gui_model.NBODY_G * 5514.0 * (4.0 / 3.0) * math.pi * 6_371_000.0**3
        self.assertEqual(gui_model.nbody_mu(5514.0, 6_371_000.0), expected)


class NumberParsingTests(unittest.TestCase):
    def test_accepts_plain_and_scientific_notation(self) -> None:
        self.assertEqual(gui_model.nbody_number("60", "刻み幅 dt"), 60.0)
        self.assertEqual(gui_model.nbody_number("3.986004418e14", "μ"), 3.986004418e14)

    def test_rejects_non_numeric_with_the_field_name(self) -> None:
        for bad in ("", "abc", "nan", "inf"):
            with self.subTest(text=bad):
                with self.assertRaises(ValueError) as caught:
                    gui_model.nbody_number(bad, "天体2 の vx")
                self.assertEqual(
                    str(caught.exception),
                    "天体2 の vx には数値を指定してください。",
                )


class ConditionsFromRowsTests(unittest.TestCase):
    def row(self, **overrides: str) -> tuple[str, ...]:
        values: dict[str, str] = {
            "name": "月",
            "density": "3344.0",
            "radius": "1737400.0",
            "x": "1.0",
            "y": "2.0",
            "z": "0.0",
            "vx": "0.0",
            "vy": "3.0",
            "vz": "0.0",
        }
        values.update(overrides)
        return (
            values["name"], values["density"], values["radius"],
            values["x"], values["y"], values["z"],
            values["vx"], values["vy"], values["vz"],
        )

    def test_parses_rows_into_conditions(self) -> None:
        conditions = gui_model.nbody_conditions_from_rows(
            [self.row()], "60", "1000"  # type: ignore[list-item]
        )
        self.assertEqual(conditions.dt, 60.0)
        self.assertEqual(conditions.max_time, 1000.0)
        body = conditions.bodies[0]
        self.assertEqual(body.name, "月")
        self.assertEqual(body.density, 3344.0)
        self.assertEqual(body.radius, 1737400.0)
        self.assertAlmostEqual(body.mu, gui_model.nbody_mu(3344.0, 1737400.0))
        self.assertEqual(body.state, (1.0, 2.0, 0.0, 0.0, 3.0, 0.0))

    def test_empty_name_falls_back_to_a_numbered_label(self) -> None:
        conditions = gui_model.nbody_conditions_from_rows(
            [self.row(name="   ")], "60", "1000"  # type: ignore[list-item]
        )
        self.assertEqual(conditions.bodies[0].name, "天体1")

    def test_rejects_an_empty_body_list(self) -> None:
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows([], "60", "1000")
        self.assertEqual(str(caught.exception), "天体を 1 つ以上指定してください。")

    def test_rejects_a_short_row(self) -> None:
        short = ("地球", "5514.0", "6371000.0", "0.0", "0.0", "0.0", "0.0", "0.0")
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows(
                [short], "60", "1000"  # type: ignore[list-item]
            )
        self.assertEqual(str(caught.exception), "天体1 の入力欄が不足しています。")

    def test_rejects_a_bad_state_field_naming_the_body_and_field(self) -> None:
        row = self.row(vx="fast")
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows(
                [row], "60", "1000"  # type: ignore[list-item]
            )
        self.assertEqual(
            str(caught.exception), "天体1 の vx には数値を指定してください。"
        )

    def test_rejects_a_bad_density_naming_the_field(self) -> None:
        row = self.row(density="dense")
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows(
                [row], "60", "1000"  # type: ignore[list-item]
            )
        self.assertEqual(
            str(caught.exception), "天体1 の体積密度 には数値を指定してください。"
        )

    def test_rejects_bad_timestep_and_time(self) -> None:
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows(
                [self.row()], "abc", "1000"  # type: ignore[list-item]
            )
        self.assertEqual(str(caught.exception), "刻み幅 dt には数値を指定してください。")
        with self.assertRaises(ValueError) as caught:
            gui_model.nbody_conditions_from_rows(
                [self.row()], "60", ""  # type: ignore[list-item]
            )
        self.assertEqual(str(caught.exception), "最大時間 には数値を指定してください。")


class ValidateConditionsTests(unittest.TestCase):
    def conditions(self, **overrides: object) -> NBodyConditions:
        values: dict = {"bodies": (spec(),), "dt": 60.0, "max_time": 100.0}
        values.update(overrides)
        return NBodyConditions(**values)  # type: ignore[arg-type]

    def test_accepts_a_reasonable_run(self) -> None:
        self.assertIsNone(gui_model.validate_nbody_conditions(self.conditions()))

    def test_rejects_non_positive_timestep(self) -> None:
        self.assertEqual(
            gui_model.validate_nbody_conditions(self.conditions(dt=0.0)),
            "刻み幅 dt は正の数で指定してください。",
        )
        self.assertEqual(
            gui_model.validate_nbody_conditions(self.conditions(dt=-1.0)),
            "刻み幅 dt は正の数で指定してください。",
        )

    def test_rejects_non_positive_max_time(self) -> None:
        self.assertEqual(
            gui_model.validate_nbody_conditions(self.conditions(max_time=0.0)),
            "最大時間は正の数で指定してください。",
        )

    def test_rejects_non_positive_density(self) -> None:
        message = gui_model.validate_nbody_conditions(
            self.conditions(bodies=(spec(density=0.0),))
        )
        self.assertEqual(message, "天体1 の体積密度は正の数で指定してください。")

    def test_rejects_non_positive_radius(self) -> None:
        message = gui_model.validate_nbody_conditions(
            self.conditions(bodies=(spec(radius=-1.0),))
        )
        self.assertEqual(message, "天体1 の半径は正の数で指定してください。")

    def test_rejects_a_run_over_the_step_budget(self) -> None:
        message = gui_model.validate_nbody_conditions(
            self.conditions(dt=1.0, max_time=float(gui_model.MAX_NBODY_STEPS + 1))
        )
        assert message is not None
        self.assertIn("推定ステップ数", message)
        self.assertIn("上限", message)
        self.assertIn(f"{gui_model.MAX_NBODY_STEPS:,}", message)

    def test_rejects_bodies_starting_at_the_same_position(self) -> None:
        twin = spec(name="天体2")
        message = gui_model.validate_nbody_conditions(
            self.conditions(bodies=(spec(), twin))
        )
        self.assertEqual(
            message,
            "天体1 と天体2 が同じ位置で開始します。"
            "重力が特異になるため開始できません。",
        )


class RunNBodyTests(unittest.TestCase):
    """The Earth–Moon preset run, shared by the assertions below."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.conditions = gui_model.nbody_preset_conditions("earth_moon")
        cls.outcome = gui_model.run_nbody(cls.conditions)

    def test_run_reaches_the_time_limit(self) -> None:
        outcome = self.outcome
        self.assertTrue(outcome.timed_out)
        self.assertAlmostEqual(
            outcome.elapsed_time, self.conditions.max_time, delta=self.conditions.dt
        )
        self.assertLessEqual(
            abs(outcome.steps - self.conditions.estimated_steps), 1
        )

    def test_frames_are_recorded_thinned_and_monotonic(self) -> None:
        frames = self.outcome.frames
        self.assertLessEqual(len(frames), gui_model.MAX_NBODY_FRAMES)
        self.assertGreater(len(frames), 1)
        self.assertEqual(frames[0].t, 0.0)
        self.assertTrue(
            all(a.t < b.t for a, b in zip(frames, frames[1:])),
            "frame times must strictly increase",
        )
        for frame in frames:
            self.assertEqual(len(frame.positions), 2)
            for position in frame.positions:
                self.assertEqual(len(position), 3)
                self.assertTrue(all(map(math.isfinite, position)))

    def test_energy_is_conserved_over_the_run(self) -> None:
        self.assertLess(abs(self.outcome.energy_drift_percent), 1e-9)

    def test_satellite_preset_records_three_bodies(self) -> None:
        conditions = gui_model.nbody_preset_conditions("earth_moon_satellite")
        outcome = gui_model.run_nbody(conditions)
        self.assertTrue(outcome.timed_out)
        self.assertEqual(len(outcome.frames[0].positions), 3)
        self.assertLess(abs(outcome.energy_drift_percent), 1e-9)

    def test_invalid_conditions_are_rejected_before_integrating(self) -> None:
        bad = NBodyConditions(bodies=(spec(),), dt=0.0, max_time=10.0)
        with self.assertRaises(ValueError) as caught:
            gui_model.run_nbody(bad)
        self.assertEqual(str(caught.exception), "刻み幅 dt は正の数で指定してください。")


class NBodyMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        conditions = gui_model.nbody_preset_conditions("earth_moon_satellite")
        cls.outcome = gui_model.run_nbody(conditions)

    def test_metric_rows_match_the_placeholder_keys(self) -> None:
        default_keys = [row[0] for row in gui_model.DEFAULT_NBODY_METRIC_ROWS]
        metric_keys = [
            row[0] for row in gui_model.nbody_result_metrics(self.outcome)
        ]
        self.assertEqual(default_keys, metric_keys)

    def test_placeholder_rows_are_dashes(self) -> None:
        for _key, _label, value in gui_model.DEFAULT_NBODY_METRIC_ROWS:
            self.assertEqual(value, "-")

    def test_values_after_a_run(self) -> None:
        values = dict(
            (key, value)
            for key, _label, value in gui_model.nbody_result_metrics(self.outcome)
        )
        self.assertEqual(values["bodies"], "3")
        self.assertEqual(values["timed_out"], "yes")
        self.assertEqual(values["steps"], "4320")
        self.assertEqual(values["frames"], str(len(self.outcome.frames)))
        self.assertTrue(values["elapsed"].endswith(" s"))
        self.assertTrue(values["energy_drift"].endswith(" %"))


class NBodyErrorLocalisationTests(unittest.TestCase):
    """nbody.py messages that errors.py rewrites (desktop-only patterns)."""

    def test_minimum_separation_is_translated(self) -> None:
        message = (
            "bodies 0 and 1 are within the 1000000 m minimum separation "
            "(distance 5 m); a close encounter cannot be modelled as point masses"
        )
        localised = errors.localize_error(message)
        self.assertNotEqual(localised, message)
        self.assertIn("最小間隔", localised)

    def test_coincident_bodies_are_translated(self) -> None:
        message = (
            "bodies 0 and 1 occupy the same position; the mutual "
            "gravitational force is singular"
        )
        localised = errors.localize_error(message)
        self.assertNotEqual(localised, message)
        self.assertIn("同じ位置", localised)

    def test_initial_speed_divergence_is_translated(self) -> None:
        message = (
            "body 0 reached a speed of 2.072e+22 m/s, more than 1000x its "
            "initial speed; the timestep is too coarse for this scenario"
        )
        localised = errors.localize_error(message)
        self.assertNotEqual(localised, message)
        self.assertIn("刻み幅 dt が大きすぎて計算速度が発散", localised)

    def test_non_finite_state_uses_the_shared_pattern(self) -> None:
        message = (
            "body 0 reached a non-finite state (0, 0, nan, 0); the timestep "
            "is too coarse for this scenario"
        )
        localised = errors.localize_error(message)
        self.assertIn("非有限値", localised)


class EqualAspectDomainTests(unittest.TestCase):
    def test_empty_input_returns_a_unit_box(self) -> None:
        self.assertEqual(
            trajectory_chart.equal_aspect_domain([], [], 600, 400),
            (-1.0, 1.0, -1.0, 1.0),
        )

    def test_domain_contains_every_point(self) -> None:
        xs = [-3.0e8, 0.0, 4.0e8]
        ys = [-1.0e8, 2.0e8]
        x_lo, x_hi, y_lo, y_hi = trajectory_chart.equal_aspect_domain(
            xs, ys, 640, 480
        )
        self.assertLessEqual(x_lo, min(xs))
        self.assertGreaterEqual(x_hi, max(xs))
        self.assertLessEqual(y_lo, min(ys))
        self.assertGreaterEqual(y_hi, max(ys))

    def test_units_per_pixel_match_on_both_axes(self) -> None:
        x_lo, x_hi, y_lo, y_hi = trajectory_chart.equal_aspect_domain(
            [0.0, 1.0e6], [0.0, 5.0e5], 800, 300
        )
        self.assertAlmostEqual(
            (x_hi - x_lo) / 800, (y_hi - y_lo) / 300, places=9
        )

    def test_degenerate_points_still_produce_a_usable_domain(self) -> None:
        x_lo, x_hi, y_lo, y_hi = trajectory_chart.equal_aspect_domain(
            [5.0], [5.0], 640, 480
        )
        self.assertLess(x_lo, 5.0)
        self.assertGreater(x_hi, 5.0)
        self.assertLess(y_lo, 5.0)
        self.assertGreater(y_hi, 5.0)
        self.assertAlmostEqual(
            (x_hi - x_lo) / 640, (y_hi - y_lo) / 480, places=9
        )

    def test_padding_widens_the_domain_beyond_the_data(self) -> None:
        x_lo, x_hi, _y_lo, _y_hi = trajectory_chart.equal_aspect_domain(
            [0.0, 100.0], [0.0, 100.0], 640, 480, pad_fraction=0.10
        )
        self.assertLess(x_lo, 0.0)
        self.assertGreater(x_hi, 100.0)


if __name__ == "__main__":
    unittest.main()
