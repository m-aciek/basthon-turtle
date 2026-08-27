import contextlib
import io
import unittest
from unittest import mock

from basthon import turtle


class ColorTests(unittest.TestCase):
    def setUp(self):
        turtle.Singleton._instances.clear()
        turtle.Turtle.screen = None
        turtle.Turtle._pen = None
        self.standalone = mock.patch.object(
            turtle._standalone, "create_session", return_value=None
        )
        self.standalone.start()

    def tearDown(self):
        self.standalone.stop()
        turtle.Singleton._instances.clear()
        turtle.Turtle.screen = None
        turtle.Turtle._pen = None

    def test_color_accepts_mutable_rgb_sequence(self):
        pen = turtle.Turtle(visible=False)

        pen.color([0.5, 0, 0])

        self.assertEqual(pen.color(), ("#800000", "#800000"))

    def test_individual_colors_accept_rgb_components_and_sequences(self):
        pen = turtle.Turtle(visible=False)

        pen.pencolor(0.5, 0, 0)
        pen.fillcolor([0, 0.5, 0])

        self.assertEqual(pen.pencolor(), "#800000")
        self.assertEqual(pen.fillcolor(), "#008000")

    def test_color_accepts_separate_rgb_sequences(self):
        pen = turtle.Turtle(visible=False)

        pen.color([0.5, 0, 0], (0, 0, 0.5))

        self.assertEqual(pen.color(), ("#800000", "#000080"))

    def test_background_accepts_rgb_components(self):
        screen = turtle.Screen()

        screen.bgcolor(0.5, 0, 0)

        self.assertEqual(screen.bgcolor(), "#800000")

    def test_color_mode_255_accepts_byte_rgb_sequences(self):
        screen = turtle.Screen()
        pen = turtle.Turtle(visible=False)

        screen.colormode(255)
        screen.bgcolor((240, 240, 255))
        pen.color([128, 0, 0])

        self.assertEqual(screen.colormode(), 255)
        self.assertEqual(screen.bgcolor(), "#f0f0ff")
        self.assertEqual(pen.color(), ("#800000", "#800000"))

    def test_rgb_components_must_be_in_default_color_range(self):
        pen = turtle.Turtle(visible=False)

        with self.assertRaisesRegex(turtle.TurtleGraphicsError, "bad color sequence"):
            pen.color([1.1, 0, 0])

    def test_turtledemo_rosette_accepts_separate_rgb_components(self):
        from turtledemo import rosette

        with (
            mock.patch.object(rosette, "sleep"),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = rosette.main()

        self.assertRegex(result, r"runtime: \d+\.\d{3} sec")


if __name__ == "__main__":
    unittest.main()
