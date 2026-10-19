"""Тесты тестового репозитория и построения графа DFS (этап 3)."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from main import (
    TestRepo, TestRepoError, parse_line, load_repo_map,
    build_dependency_graph,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class FakeSource:
    """Заглушка источника зависимостей для быстрых тестов графа."""

    def __init__(self, repo_map):
        """Инициализирует экземпляр."""
        self.repo_map = repo_map

    def get_direct_deps(self, package, version=None):
        """Проверка: get direct deps."""
        return list(self.repo_map[package])


class TestTestRepo(unittest.TestCase):
    """Проверки разбора файла тестового репозитория."""

    def test_parse_line(self):
        """Проверка: parse line."""
        self.assertEqual(parse_line("A : B, C"), ("A", ["B", "C"]))

    def test_parse_line_without_deps(self):
        """Проверка: parse line without deps."""
        self.assertEqual(parse_line("D :"), ("D", []))

    def test_parse_line_bad_format(self):
        """Проверка: parse line bad format."""
        with self.assertRaises(TestRepoError):
            parse_line("A B C")

    def test_load_missing_file(self):
        """Проверка: load missing file."""
        with self.assertRaises(TestRepoError):
            load_repo_map(os.path.join(FIXTURES, "no_such_file.txt"))

    def test_basic_fixture(self):
        """Проверка: basic fixture."""
        repo = TestRepo(os.path.join(FIXTURES, "repo_basic.txt"))
        self.assertEqual(repo.get_direct_deps("A"), ["B", "C"])

    def test_unknown_package(self):
        """Проверка: unknown package."""
        repo = TestRepo(os.path.join(FIXTURES, "repo_basic.txt"))
        with self.assertRaises(TestRepoError):
            repo.get_direct_deps("Z")


class TestDependencyGraph(unittest.TestCase):
    """Проверки обхода DFS без рекурсии, фильтра и циклов."""

    def test_transitive_graph(self):
        """Проверка: transitive graph."""
        source = FakeSource({"A": ["B"], "B": ["C"], "C": []})
        edges, warnings = build_dependency_graph(
            source, "A", "1.0.0", ""
        )
        self.assertEqual(edges, {"A": ["B"], "B": ["C"], "C": []})
        self.assertEqual(warnings, [])

    def test_filter_skips_subtree(self):
        """Проверка: filter skips subtree."""
        source = FakeSource({"A": ["FOO"], "FOO": ["X"], "X": []})
        edges, _ = build_dependency_graph(source, "A", "1.0.0", "FOO")
        self.assertEqual(edges, {"A": []})

    def test_cycle_handled(self):
        """Проверка: cycle handled."""
        source = FakeSource({"A": ["B"], "B": ["A"]})
        edges, warnings = build_dependency_graph(
            source, "A", "1.0.0", ""
        )
        self.assertEqual(edges["A"], ["B"])
        self.assertEqual(edges["B"], ["A"])
        self.assertTrue(warnings)

    def test_transitive_versions_resolved(self):
        """Проверка: transitive versions resolved."""
        class Recording:
            """Проверка: Recording."""
            def __init__(self):
                """Инициализирует экземпляр."""
                self.calls = []

            def get_direct_deps(self, package, version=None):
                """Проверка: get direct deps."""
                self.calls.append((package, version))
                deps = {"A": ["B"], "B": []}
                return deps.get(package, [])

        source = Recording()
        build_dependency_graph(source, "A", "1.0.0", "")
        self.assertIn(("A", "1.0.0"), source.calls)
        self.assertIn(("B", None), source.calls)

    def test_deep_chain_without_recursion(self):
        """Проверка: deep chain without recursion."""
        size = 3000
        repo_map = {
            f"N{index:04d}": [f"N{index + 1:04d}"]
            for index in range(size)
        }
        repo_map[f"N{size:04d}"] = []
        source = FakeSource(repo_map)
        edges, _ = build_dependency_graph(
            source, "N0000", "1.0.0", ""
        )
        self.assertEqual(len(edges), size + 1)


if __name__ == "__main__":
    unittest.main()
