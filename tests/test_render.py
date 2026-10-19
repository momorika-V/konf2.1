"""Тесты визуализации: PlantUML-текст и генерация PNG (этап 5)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from main import (
    build_plantuml, render_diagram_png, FONT, FONT_HEIGHT, GLYPH_WIDTH,
)

MIN_PNG_BYTES = 100
EMPTY_SIZE = 0


class TestFont(unittest.TestCase):
    """Проверки целостности растрового шрифта."""

    def test_all_glyphs_have_correct_shape(self):
        """Проверка: all glyphs have correct shape."""
        for char, glyph in FONT.items():
            message = f"Некорректный глиф: {char!r}"
            self.assertEqual(len(glyph), FONT_HEIGHT, message)
            for row in glyph:
                self.assertEqual(len(row), GLYPH_WIDTH, message)
                self.assertTrue(set(row) <= {"#", "."}, message)


class TestPlantUml(unittest.TestCase):
    """Проверки текстового представления графа."""

    def test_basic_diagram(self):
        """Проверка: basic diagram."""
        edges = {"A": ["B"], "B": []}
        text = build_plantuml(edges)
        self.assertIn("@startuml", text)
        self.assertIn("@enduml", text)
        self.assertIn("[A] --> [B]", text)

    def test_sorted_output(self):
        """Проверка: sorted output."""
        edges = {"B": ["A"], "A": ["Z"]}
        lines = build_plantuml(edges).splitlines()
        first_edge = lines[1]
        self.assertTrue(first_edge.strip().startswith("[A]"))


class TestPngRender(unittest.TestCase):
    """Проверки сохранения PNG-файла."""

    def test_png_file_created(self):
        """Проверка: png file created."""
        edges = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        handle, path = tempfile.mkstemp(suffix=".png")
        os.close(handle)
        try:
            render_diagram_png(edges, "A", path)
            with open(path, "rb") as saved:
                data = saved.read()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(data), MIN_PNG_BYTES)
        finally:
            os.remove(path)

    def test_single_node(self):
        """Проверка: single node."""
        handle, path = tempfile.mkstemp(suffix=".png")
        os.close(handle)
        try:
            render_diagram_png({"A": []}, "A", path)
            self.assertTrue(os.path.getsize(path) > EMPTY_SIZE)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
