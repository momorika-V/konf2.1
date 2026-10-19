"""Тесты разбора и проверки параметров командной строки (этап 1)."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "src")
)

from main import ConfigError, parse_config

GOOD_ARGS = [
    "--package", "serde", "--version", "1.0.210",
    "--repo-url", "https://index.crates.io", "--output", "g.png",
]


class TestConfig(unittest.TestCase):
    """Проверки корректных и ошибочных конфигураций."""

    def test_valid_config_fields(self):
        """Проверка: valid config fields."""
        config = parse_config(GOOD_ARGS + ["--filter", "rand"])
        self.assertEqual(config.package, "serde")
        self.assertEqual(config.version, "1.0.210")
        self.assertEqual(config.filter_substring, "rand")
        self.assertFalse(config.test_mode)

    def test_missing_package(self):
        """Проверка: missing package."""
        args = ["--version", "1.0.0", "--repo-url",
                "https://x", "--output", "g.png"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_missing_version(self):
        """Проверка: missing version."""
        args = ["--package", "a", "--repo-url",
                "https://x", "--output", "g.png"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_bad_output_extension(self):
        """Проверка: bad output extension."""
        args = ["--package", "a", "--version", "1.0.0",
                "--repo-url", "https://x", "--output", "g.jpg"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_no_source(self):
        """Проверка: no source."""
        args = ["--package", "a", "--version", "1.0.0",
                "--output", "g.png"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_both_sources(self):
        """Проверка: both sources."""
        args = GOOD_ARGS + ["--test-mode",
                            "--test-repo", "tests/fixtures/repo_basic.txt"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_test_mode_requires_path(self):
        """Проверка: mode requires path."""
        args = ["--package", "A", "--version", "1.0.0",
                "--test-mode", "--output", "g.png"]
        with self.assertRaises(ConfigError):
            parse_config(args)

    def test_print_config_flag(self):
        """Проверка: print config flag."""
        config = parse_config(GOOD_ARGS + ["--print-config"])
        self.assertTrue(config.print_config)

    def test_as_pairs_contains_all_params(self):
        """Проверка: as pairs contains all params."""
        config = parse_config(GOOD_ARGS)
        keys = [key for key, _ in config.as_pairs()]
        expected = ["package", "version", "repo_url", "test_repo_path",
                    "test_mode", "output_file", "filter_substring"]
        self.assertEqual(keys, expected)


if __name__ == "__main__":
    unittest.main()
