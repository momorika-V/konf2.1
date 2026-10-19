"""Тесты порядка загрузки зависимостей (этап 4)."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from main import get_load_order


class TestLoadOrder(unittest.TestCase):
    """Проверки пост-порядка обхода графа зависимостей."""

    def test_dependencies_come_first(self):
        """Проверка: dependencies come first."""
        edges = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        order = get_load_order(edges, "A")
        self.assertEqual(order, ["D", "B", "C"])

    def test_root_excluded(self):
        """Проверка: root excluded."""
        edges = {"A": ["B"], "B": []}
        order = get_load_order(edges, "A")
        self.assertNotIn("A", order)
        self.assertEqual(order, ["B"])

    def test_cycle_does_not_hang(self):
        """Проверка: cycle does not hang."""
        edges = {"A": ["B"], "B": ["C"], "C": ["B"]}
        order = get_load_order(edges, "A")
        self.assertEqual(order, ["C", "B"])

    def test_no_dependencies(self):
        """Проверка: no dependencies."""
        edges = {"A": []}
        self.assertEqual(get_load_order(edges, "A"), [])


if __name__ == "__main__":
    unittest.main()
