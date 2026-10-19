"""Тесты Cargo-индекса: пути, разбор JSONL, выбор версии (этап 2)."""

import json
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from main import (
    build_index_path, build_index_url, parse_entries,
    select_version, select_newest_version, version_key,
    extract_direct_deps, CargoIndexError,
)

ENTRY_V1 = {
    "name": "sample", "vers": "1.0.0",
    "deps": [
        {"name": "dep_a", "req": "^1.0", "kind": None},
        {"name": "dep_b", "req": "^2.0", "kind": "normal"},
        {"name": "dep_c", "req": "^3.0", "kind": "dev"},
        {"name": "dep_d", "req": "^4.0", "kind": "build"},
        {"name": "dep_e", "req": "^5.0", "kind": None, "optional": True},
    ],
}


class TestCargoIndex(unittest.TestCase):
    """Проверки логики sparse-индекса без сетевых обращений."""

    def test_index_path_single_char(self):
        """Проверка: index path single char."""
        self.assertEqual(build_index_path("a"), "1/a")

    def test_index_path_two_chars(self):
        """Проверка: index path two chars."""
        self.assertEqual(build_index_path("ab"), "2/ab")

    def test_index_path_three_chars(self):
        """Проверка: index path three chars."""
        self.assertEqual(build_index_path("abc"), "3/a/abc")

    def test_index_path_long_name(self):
        """Проверка: index path long name."""
        self.assertEqual(build_index_path("serde"), "se/rd/serde")

    def test_index_url(self):
        """Проверка: index url."""
        url = build_index_url("https://index.crates.io/", "serde")
        self.assertEqual(url, "https://index.crates.io/se/rd/serde")

    def test_parse_entries_jsonl(self):
        """Проверка: parse entries jsonl."""
        text = json.dumps(ENTRY_V1) + "\n" + json.dumps(ENTRY_V1) + "\n"
        entries = parse_entries(text)
        self.assertEqual(len(entries), 2)

    def test_parse_entries_skips_empty_lines(self):
        """Проверка: parse entries skips empty lines."""
        entries = parse_entries("\n\n")
        self.assertEqual(entries, [])

    def test_select_version_found(self):
        """Проверка: select version found."""
        entry = select_version([ENTRY_V1], "1.0.0")
        self.assertEqual(entry["vers"], "1.0.0")

    def test_select_version_missing(self):
        """Проверка: select version missing."""
        with self.assertRaises(CargoIndexError):
            select_version([ENTRY_V1], "9.9.9")

    def test_direct_deps_excludes_dev_build_optional(self):
        """Проверка: direct deps excludes dev build optional."""
        deps = extract_direct_deps(ENTRY_V1)
        self.assertEqual(deps, ["dep_a", "dep_b"])

    def test_version_key_numeric_order(self):
        """Проверка: version key numeric order."""
        versions = ["1.10.0", "1.2.0", "1.9.9"]
        ordered = sorted(versions, key=version_key)
        self.assertEqual(ordered, ["1.2.0", "1.9.9", "1.10.0"])

    def test_select_newest_version(self):
        """Проверка: select newest version."""
        first = dict(ENTRY_V1, vers="1.2.0")
        second = dict(ENTRY_V1, vers="1.10.0")
        third = dict(ENTRY_V1, vers="1.9.0")
        newest = select_newest_version([first, second, third])
        self.assertEqual(newest["vers"], "1.10.0")


if __name__ == "__main__":
    unittest.main()
