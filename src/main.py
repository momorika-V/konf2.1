"""CLI-приложение визуализации графа зависимостей пакетов Cargo.

Вариант 22. Все этапы собраны в одном файле main.py, секции идут
в порядке этапов задания:
  Этап 1 - конфигурация командной строки и обработка ошибок.
  Этап 2 - получение прямых зависимостей из sparse-индекса Cargo.
  Этап 3 - граф зависимостей DFS без рекурсии, тестовый репозиторий.
  Этап 4 - порядок загрузки зависимостей.
  Этап 5 - визуализация PlantUML и PNG (собственный кодировщик).

Сторонние библиотеки и менеджеры пакетов не используются: только
стандартная библиотека Python (требование задания, этап 2).
"""

import argparse
import json
import os
import struct
import sys
import urllib.request
import zlib

EXIT_OK = 0
EXIT_ERROR = 1

""" Единые состояния раскраски вершин для всех обходов графа: """
""" DFS построения графа, поиска циклов и порядка загрузки. """
STATE_NEW = 0
STATE_OPEN = 1
STATE_CLOSED = 2


""" Этап 1. Конфигурация командной строки """
DEFAULT_FILTER = ""
PNG_EXTENSION = ".png"


class ConfigError(Exception):
    """Ошибка некорректных параметров командной строки."""


class Config:
    """Хранилище параметров командной строки приложения."""

    def __init__(self, namespace):
        """Инициализирует экземпляр."""
        self.package = namespace.package
        self.version = namespace.version
        self.repo_url = namespace.repo_url
        self.test_repo_path = namespace.test_repo
        self.test_mode = namespace.test_mode
        self.output_file = namespace.output
        self.filter_substring = namespace.filter_substring
        self.print_config = namespace.print_config
        self.direct_only = namespace.direct_deps
        self.load_order = namespace.load_order

    def as_pairs(self):
        """Вернуть параметры списком пар ключ-значение для вывода."""
        return [
            ("package", self.package),
            ("version", self.version),
            ("repo_url", self.repo_url),
            ("test_repo_path", self.test_repo_path),
            ("test_mode", self.test_mode),
            ("output_file", self.output_file),
            ("filter_substring", self.filter_substring),
        ]


def build_parser():
    """Создать парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Визуализация графа зависимостей пакетов Cargo"
    )
    parser.add_argument("--package", help="имя анализируемого пакета")
    parser.add_argument("--version", help="версия пакета")
    parser.add_argument(
        "--repo-url", help="URL-адрес репозитория пакетов"
    )
    parser.add_argument(
        "--test-repo", help="путь к файлу тестового репозитория"
    )
    parser.add_argument(
        "--test-mode", action="store_true",
        help="режим работы с тестовым репозиторием",
    )
    parser.add_argument(
        "--output", help="имя генерируемого файла изображения (.png)"
    )
    parser.add_argument(
        "--filter", dest="filter_substring", default=DEFAULT_FILTER,
        help="подстрока для фильтрации пакетов",
    )
    parser.add_argument(
        "--print-config", action="store_true",
        help="вывести параметры ключ-значение и завершить работу",
    )
    parser.add_argument(
        "--direct-deps", action="store_true",
        help="вывести только прямые зависимости (демо этапа 2)",
    )
    parser.add_argument(
        "--load-order", action="store_true",
        help="вывести порядок загрузки зависимостей (этап 4)",
    )
    return parser


def validate_pair(config):
    """Проверить совместимость источника данных: URL или тестовый."""
    has_url = config.repo_url is not None
    has_test = config.test_mode or config.test_repo_path is not None
    if has_url and has_test:
        raise ConfigError(
            "Заданы одновременно repo-url и тестовый репозиторий"
        )
    if not has_url and not has_test:
        raise ConfigError(
            "Не задан источник данных: repo-url или test-repo"
        )


def validate_required(config):
    """Проверить наличие обязательных параметров и формата вывода."""
    if not config.package:
        raise ConfigError("Не задано имя пакета (--package)")
    if not config.version:
        raise ConfigError("Не задана версия пакета (--version)")
    if not config.output_file:
        raise ConfigError("Не задано имя файла вывода (--output)")
    if not config.output_file.endswith(PNG_EXTENSION):
        raise ConfigError("Файл вывода должен иметь расширение .png")


def validate_values(config):
    """Проверить допустимость значений отдельных параметров."""
    if config.test_mode and not config.test_repo_path:
        raise ConfigError(
            "Режим тестирования требует путь (--test-repo)"
        )
    if config.test_repo_path and not config.test_mode:
        raise ConfigError(
            "Путь test-repo требует режима (--test-mode)"
        )
    if config.filter_substring != DEFAULT_FILTER:
        if not config.filter_substring.strip():
            raise ConfigError("Фильтр состоит из пробелов")


def parse_config(argv):
    """Разобрать и проверить параметры; вернуть объект Config."""
    namespace = build_parser().parse_args(argv)
    config = Config(namespace)
    validate_required(config)
    validate_pair(config)
    validate_values(config)
    return config


def print_config(config):
    """Вывести все параметры в формате ключ-значение (этап 1)."""
    for key, value in config.as_pairs():
        print(f"{key} = {value}")


""" Этап 2. Сбор данных из sparse-индекса Cargo"""
DEFAULT_INDEX_URL = "https://index.crates.io"
HTTP_TIMEOUT_SECONDS = 30
NORMAL_KINDS = (None, "normal")
NAME_LEN_SINGLE = 1
NAME_LEN_DOUBLE = 2
NAME_LEN_TRIPLE = 3
USER_AGENT = "dep-graph-visualizer"
MAX_LISTED_VERSIONS = 20


class CargoIndexError(Exception):
    """Ошибка получения или разбора данных индекса Cargo."""


def build_index_path(package):
    """Построить путь пакета в sparse-индексе по правилам Cargo."""
    name_len = len(package)
    if name_len == NAME_LEN_SINGLE:
        return f"1/{package}"
    if name_len == NAME_LEN_DOUBLE:
        return f"2/{package}"
    if name_len == NAME_LEN_TRIPLE:
        return f"3/{package[0]}/{package}"
    return f"{package[:2]}/{package[2:4]}/{package}"


def build_index_url(index_url, package):
    """Собрать полный URL записи пакета в sparse-индексе."""
    base = index_url.rstrip("/")
    return f"{base}/{build_index_path(package)}"


def fetch_text(url):
    """Скачать текстовый ресурс по HTTP и вернуть его содержимое."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=HTTP_TIMEOUT_SECONDS
        ) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset)
    except OSError as error:
        raise CargoIndexError(
            f"Не удалось скачать {url}: {error}"
        ) from error


def parse_entries(text):
    """Разобрать текст индекса: по одной JSON-записи на строку."""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def select_version(entries, version):
    """Найти запись индекса для заданной версии пакета."""
    for entry in entries:
        if entry.get("vers") == version:
            return entry
    available = sorted({entry.get("vers") for entry in entries})
    listed = available[:MAX_LISTED_VERSIONS]
    note = f" (всего {len(available)})"
    raise CargoIndexError(
        f"Версия {version} не найдена. Доступны: "
        f"{', '.join(listed)}{note}"
    )


def version_key(vers):
    """Ключ сортировки версий: числовые компоненты через точку."""
    parts = []
    for chunk in vers.split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits))
    return parts


def select_newest_version(entries):
    """Выбрать запись с новейшей версией (для транзитивных узлов)."""
    return max(entries, key=lambda entry: version_key(entry["vers"]))


def extract_direct_deps(entry):
    """Извлечь имена прямых (normal) зависимостей из записи."""
    names = []
    for dep in entry.get("deps", []):
        kind = dep.get("kind")
        if kind in NORMAL_KINDS and dep.get("optional") is not True:
            names.append(dep["name"])
    return sorted(set(names))


class CargoIndex:
    """Источник прямых зависимостей через sparse-индекс Cargo."""

    def __init__(self, index_url):
        """Инициализирует экземпляр."""
        self.index_url = index_url

    def get_direct_deps(self, package, version=None):
        """Вернуть прямые зависимости пакета.

        Для заданной версии выбирается точная запись индекса;
        если версия не задана (транзитивный узел), берётся новейшая.
        """
        url = build_index_url(self.index_url, package)
        entries = parse_entries(fetch_text(url))
        if version is None:
            entry = select_newest_version(entries)
        else:
            entry = select_version(entries, version)
        return extract_direct_deps(entry)


""" Этап 3. Тестовый репозиторий и граф зависимостей"""
SEPARATOR = ":"
COMMENT_PREFIX = "#"


class TestRepoError(Exception):
    """Ошибка чтения или разбора файла тестового репозитория."""


def parse_line(line):
    """Разобрать одну строку: вернуть пару (пакет, список зависимостей)."""
    if SEPARATOR not in line:
        raise TestRepoError(f"Нет разделителя '{SEPARATOR}': {line}")
    left, right = line.split(SEPARATOR, 1)
    package = left.strip()
    deps = [part.strip() for part in right.split(",")]
    deps = [dep for dep in deps if dep]
    if not package:
        raise TestRepoError(f"Пустое имя пакета: {line}")
    return package, deps


def load_repo_map(path):
    """Прочитать файл тестового репозитория в словарь зависимостей."""
    repo_map = {}
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as error:
        raise TestRepoError(
            f"Не удалось прочитать файл: {error}"
        ) from error
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(COMMENT_PREFIX):
            continue
        try:
            package, deps = parse_line(line)
        except TestRepoError as error:
            raise TestRepoError(f"Строка {number}: {error}") from error
        repo_map[package] = deps
    return repo_map


class TestRepo:
    """Источник зависимостей для режима тестирования (этап 3)."""

    def __init__(self, path):
        """Инициализирует экземпляр."""
        self.repo_map = load_repo_map(path)

    def get_direct_deps(self, package, version=None):
        """Вернуть прямые зависимости пакета из файла репозитория."""
        if package not in self.repo_map:
            raise TestRepoError(f"Пакет {package} отсутствует в репозитории")
        return list(self.repo_map[package])


def is_filtered(name, filter_substring):
    """Определить, должен ли пакет быть исключён из анализа."""
    return bool(filter_substring) and filter_substring in name


def version_for(root, package, version):
    """Версия запроса: для корня - заданная, для остальных - новейшая."""
    if package == root:
        return version
    return None


def discover_neighbours(
    stack, source, root, package, version, filter_substring, colors
):
    """Положить соседей вершины на стек с учётом фильтра и циклов."""
    for dep in source.get_direct_deps(
        package, version_for(root, package, version)
    ):
        if is_filtered(dep, filter_substring):
            continue
        if colors.get(dep, STATE_NEW) == STATE_OPEN:
            continue
        stack.append(dep)


def walk(source, root, version, filter_substring):
    """Итеративный DFS: вернуть множество посещённых пакетов."""
    colors = {root: STATE_OPEN}
    stack = []
    discover_neighbours(
        stack, source, root, root, version, filter_substring, colors
    )
    while stack:
        package = stack.pop()
        if colors.get(package, STATE_NEW) != STATE_NEW:
            continue
        colors[package] = STATE_OPEN
        discover_neighbours(
            stack, source, root, package, version,
            filter_substring, colors,
        )
        colors[package] = STATE_CLOSED
    return set(colors)


def build_edges(source, root, visited, version, filter_substring):
    """Собрать рёбра графа для всех посещённых пакетов."""
    edges = {}
    for package in sorted(visited):
        deps = source.get_direct_deps(
            package, version_for(root, package, version)
        )
        kept = [
            dep for dep in deps
            if not is_filtered(dep, filter_substring)
        ]
        edges[package] = sorted(kept)
    return edges


def visit_for_cycles(node, edges, colors, warnings):
    """Итеративный обход одного дерева поиска для поиска циклов."""
    stack = [(node, iter(edges.get(node, [])))]
    colors[node] = STATE_OPEN
    while stack:
        current, neighbours = stack[-1]
        found_next = False
        for neighbour in neighbours:
            state = colors.get(neighbour, STATE_NEW)
            if state == STATE_OPEN:
                warnings.append(f"Обнаружен цикл: {current} -> {neighbour}")
            elif state == STATE_NEW:
                colors[neighbour] = STATE_OPEN
                stack.append((neighbour, iter(edges.get(neighbour, []))))
                found_next = True
                break
        if not found_next:
            colors[current] = STATE_CLOSED
            stack.pop()


def find_cycles(edges):
    """Найти циклы в графе и вернуть список описаний предупреждений."""
    colors = {}
    warnings = []
    for start in sorted(edges):
        visit_for_cycles(start, edges, colors, warnings)
    return warnings


def build_dependency_graph(source, root, version, filter_substring):
    """Построить граф: вернуть (рёбра, предупреждения о циклах)."""
    visited = walk(source, root, version, filter_substring)
    edges = build_edges(
        source, root, visited, version, filter_substring
    )
    warnings = find_cycles(edges)
    return edges, warnings


""" Этап 4. Порядок загрузки зависимостей"""
def iter_neighbours(edges, package):
    """Вернуть соседей пакета в отсортированном (стабильном) порядке."""
    return sorted(edges.get(package, []))


def process_next(stack, edges, colors, order):
    """Обработать вершину со стека: развернуть или закрыть её."""
    package, neighbours = stack[-1]
    for neighbour in neighbours:
        state = colors.get(neighbour, STATE_NEW)
        if state == STATE_NEW:
            colors[neighbour] = STATE_OPEN
            stack.append(
                (neighbour, iter(iter_neighbours(edges, neighbour)))
            )
            return
        if state == STATE_OPEN:
            order.append((package, neighbour))
    colors[package] = STATE_CLOSED
    order.append(package)
    stack.pop()


def get_load_order(edges, root):
    """Вернуть список зависимостей в порядке их загрузки.

    Пост-порядок обхода: зависимость появляется в списке раньше
    использующего её пакета. Циклы не приводят к зависанию, корень
    в порядок загрузки не включается.
    """
    colors = {root: STATE_OPEN}
    stack = [(root, iter(iter_neighbours(edges, root)))]
    order = []
    while stack:
        process_next(stack, edges, colors, order)
    return [
        item for item in order
        if isinstance(item, str) and item != root
    ]


"""Этап 5. Визуализация: PlantUML, шрифт, холст, PNG, компоновка"""
START_MARKER = "@startuml"
END_MARKER = "@enduml"
INDENT = "  "


def format_edge(source, target):
    """Отформатировать одно ребро графа в синтаксисе PlantUML."""
    return f"[{source}] --> [{target}]"


def build_plantuml(edges):
    """Построить полный текст диаграммы PlantUML по рёбрам графа."""
    lines = [START_MARKER]
    for source in sorted(edges):
        for target in edges[source]:
            lines.append(INDENT + format_edge(source, target))
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def save_plantuml(edges, path):
    """Сохранить текст PlantUML в файл с заданным именем."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_plantuml(edges))


FONT_HEIGHT = 7
GLYPH_WIDTH = 5
GLYPH_STEP = 6

EMPTY_GLYPH = ["....."] * FONT_HEIGHT

FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "a": [".....", ".....", ".###.", "....#", ".####", "#...#", ".####"],
    "b": ["#....", "#....", "####.", "#...#", "#...#", "#...#", "####."],
    "c": [".....", ".....", ".###.", "#....", "#....", "#...#", ".###."],
    "d": ["....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"],
    "e": [".....", ".....", ".###.", "#...#", "#####", "#....", ".###."],
    "f": ["..##.", ".#..#", ".#...", "####.", ".#...", ".#...", ".#..."],
    "g": [".....", ".####", "#...#", "#...#", ".####", "....#", ".###."],
    "h": ["#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"],
    "i": ["..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."],
    "j": ["...#.", ".....", "..##.", "...#.", "...#.", "#..#.", ".##.."],
    "k": ["#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."],
    "l": [".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "m": [".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"],
    "n": [".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "p": [".....", ".....", "####.", "#...#", "#...#", "####.", "#...."],
    "q": [".....", ".....", ".####", "#...#", "#...#", ".####", "....#"],
    "r": [".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."],
    "s": [".....", ".....", ".####", "#....", ".###.", "....#", "####."],
    "t": [".#...", ".#...", "####.", ".#...", ".#...", ".#..#", "..##."],
    "u": [".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"],
    "v": [".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "w": [".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."],
    "x": [".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
    "y": [".....", ".....", "#...#", "#...#", ".####", "....#", ".###."],
    "z": [".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


def get_glyph(char):
    """Вернуть глиф символа или заглушку для неизвестного символа."""
    return FONT.get(char, EMPTY_GLYPH)


BYTES_PER_PIXEL = 3


class Canvas:
    """RGB-холст с операциями рисования и сохранением в PNG."""

    def __init__(self, width, height, background):
        """Инициализирует экземпляр."""
        self.width = width
        self.height = height
        self.pixels = [
            bytearray(background * width) for _ in range(height)
        ]

    def set_pixel(self, x, y, color):
        """Закрасить один пиксель, если он внутри холста."""
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = x * BYTES_PER_PIXEL
            self.pixels[y][offset:offset + BYTES_PER_PIXEL] = color

    def fill_rect(self, x, y, width, height, color):
        """Закрасить прямоугольник заданного размера."""
        for row in range(y, y + height):
            for column in range(x, x + width):
                self.set_pixel(column, row, color)

    def draw_rect(self, x, y, width, height, color):
        """Нарисовать контур прямоугольника."""
        self.fill_rect(x, y, width, 1, color)
        self.fill_rect(x, y + height - 1, width, 1, color)
        self.fill_rect(x, y, 1, height, color)
        self.fill_rect(x + width - 1, y, 1, height, color)

    def draw_line(self, x1, y1, x2, y2, color):
        """Нарисовать отрезок алгоритмом Брезенхема."""
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        step_x = 1 if x1 < x2 else -1
        step_y = 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            self.set_pixel(x1, y1, color)
            if x1 == x2 and y1 == y2:
                return
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x1 += step_x
            if doubled <= dx:
                error += dx
                y1 += step_y

    def draw_char(self, char, x, y, color, scale):
        """Нарисовать один символ шрифта с масштабированием."""
        glyph = get_glyph(char)
        for row_index, row in enumerate(glyph):
            for column_index, cell in enumerate(row):
                if cell == "#":
                    self.fill_rect(
                        x + column_index * scale,
                        y + row_index * scale,
                        scale, scale, color,
                    )

    def draw_text(self, text, x, y, color, scale):
        """Нарисовать строку текста шрифтом 5x7."""
        cursor = x
        for char in text:
            self.draw_char(char, cursor, y, color, scale)
            cursor += GLYPH_STEP * scale

    def save(self, path):
        """Сохранить холст в PNG-файл через собственный кодировщик."""
        save_png(path, self.pixels, self.width, self.height)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR_TYPE_RGB = 2
BITS_PER_CHANNEL = 8
FILTER_NONE = 0
COMPRESSION_LEVEL = 9


def make_chunk(chunk_type, data):
    """Собрать один чанк PNG: длина, тип, данные и контрольная сумма."""
    length = struct.pack(">I", len(data))
    body = chunk_type + data
    checksum = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return length + body + checksum


def make_ihdr(width, height):
    """Сформировать заголовок IHDR для RGB-изображения."""
    params = struct.pack(
        ">IIBBBBB", width, height, BITS_PER_CHANNEL,
        COLOR_TYPE_RGB, FILTER_NONE, FILTER_NONE, FILTER_NONE,
    )
    return make_chunk(b"IHDR", params)


def make_idat(pixels, width, height):
    """Сжать пиксельные данные: фильтр None для каждой строки."""
    raw = bytearray()
    for row in pixels:
        raw.append(FILTER_NONE)
        raw.extend(row)
    compressed = zlib.compress(bytes(raw), COMPRESSION_LEVEL)
    return make_chunk(b"IDAT", compressed)


def make_iend():
    """Сформировать завершающий чанк IEND."""
    return make_chunk(b"IEND", b"")


def save_png(path, pixels, width, height):
    """Записать RGB-изображение в PNG-файл по указанному пути."""
    with open(path, "wb") as handle:
        handle.write(PNG_SIGNATURE)
        handle.write(make_ihdr(width, height))
        handle.write(make_idat(pixels, width, height))
        handle.write(make_iend())


BACKGROUND = (255, 255, 255)
BOX_COLOR = (70, 110, 190)
TEXT_COLOR = (0, 0, 0)
ARROW_COLOR = (60, 60, 60)

MARGIN = 30
CELL_WIDTH = 190
CELL_HEIGHT = 80
NODE_MIN_WIDTH = 130
NODE_PADDING = 20
NODE_HEIGHT = 46
TEXT_SCALE = 2
ARROW_HEAD = 8


def compute_levels(edges, root):
    """Вычислить уровень каждого узла (обход в ширину от корня)."""
    levels = {root: 0}
    frontier = [root]
    while frontier:
        next_frontier = []
        for node in frontier:
            for dep in edges.get(node, []):
                if dep not in levels:
                    levels[dep] = levels[node] + 1
                    next_frontier.append(dep)
        frontier = next_frontier
    return levels


def compute_positions(edges, root):
    """Разложить узлы по колонкам уровней; вернуть позиции и размеры."""
    levels = compute_levels(edges, root)
    columns = {}
    for node in sorted(levels):
        columns.setdefault(levels[node], []).append(node)
    positions = {}
    for level, nodes in columns.items():
        for index, node in enumerate(nodes):
            x = MARGIN + level * CELL_WIDTH
            y = MARGIN + index * CELL_HEIGHT
            positions[node] = (x, y)
    rows = max(len(nodes) for nodes in columns.values())
    return positions, len(columns), rows


def measure_node_width(names):
    """Подобрать ширину узла под самое длинное имя пакета."""
    char_step = 6 * TEXT_SCALE
    widest = max(len(name) * char_step for name in names)
    return max(NODE_MIN_WIDTH, widest + NODE_PADDING * 2)


def draw_label(canvas, name, box_x, box_y, node_width):
    """Нарисовать подпись узла по центру прямоугольника."""
    char_step = 6 * TEXT_SCALE
    text_w = len(name) * char_step - TEXT_SCALE
    text_h = FONT_HEIGHT * TEXT_SCALE
    x = box_x + (node_width - text_w) // 2
    y = box_y + (NODE_HEIGHT - text_h) // 2
    canvas.draw_text(name, x, y, TEXT_COLOR, TEXT_SCALE)


def draw_nodes(canvas, positions, node_width):
    """Нарисовать все узлы графа с подписями."""
    for name, (x, y) in positions.items():
        canvas.draw_rect(x, y, node_width, NODE_HEIGHT, BOX_COLOR)
        draw_label(canvas, name, x, y, node_width)


def draw_arrow(canvas, start, end, node_width):
    """Нарисовать стрелку от правой грани узла-источника к цели."""
    x1 = start[0] + node_width
    y1 = start[1] + NODE_HEIGHT // 2
    x2 = end[0]
    y2 = end[1] + NODE_HEIGHT // 2
    canvas.draw_line(x1, y1, x2, y2, ARROW_COLOR)
    canvas.draw_line(x2, y2, x2 - ARROW_HEAD, y2 - ARROW_HEAD, ARROW_COLOR)
    canvas.draw_line(x2, y2, x2 - ARROW_HEAD, y2 + ARROW_HEAD, ARROW_COLOR)


def draw_arrows(canvas, positions, edges, node_width):
    """Нарисовать все рёбра графа."""
    for source in sorted(edges):
        for target in edges[source]:
            draw_arrow(
                canvas, positions[source], positions[target], node_width
            )


def render_diagram_png(edges, root, path):
    """Построить изображение графа и сохранить его в PNG-файл."""
    positions, columns, rows = compute_positions(edges, root)
    node_width = measure_node_width(positions)
    width = MARGIN * 2 + (columns - 1) * CELL_WIDTH + node_width
    height = MARGIN * 2 + (rows - 1) * CELL_HEIGHT + NODE_HEIGHT
    canvas = Canvas(width, height, BACKGROUND)
    draw_arrows(canvas, positions, edges, node_width)
    draw_nodes(canvas, positions, node_width)
    canvas.save(path)


""" Точка входа CLI-приложения"""
def build_source(config):
    """Создать источник данных о зависимостях по конфигурации."""
    if config.test_mode:
        return TestRepo(config.test_repo_path)
    return CargoIndex(config.repo_url)


def run_direct_mode(source, config):
    """Вывести только прямые зависимости заданного пакета (этап 2)."""
    deps = source.get_direct_deps(config.package, config.version)
    print(f"Прямые зависимости {config.package}:")
    for dep in deps:
        print(f"  {dep}")


def run_full_mode(source, config):
    """Построить граф, вывести порядок загрузки и визуализацию."""
    edges, warnings = build_dependency_graph(
        source, config.package, config.version, config.filter_substring
    )
    for warning in warnings:
        print(f"Предупреждение: {warning}")
    if config.load_order:
        order = get_load_order(edges, config.package)
        print("Порядок загрузки зависимостей:")
        for name in order:
            print(f"  {name}")
    puml_path, png_path = save_outputs(edges, config)
    print(f"PlantUML сохранён: {puml_path}")
    print(f"PNG сохранён: {png_path}")
    print(f"Пакетов в графе: {len(edges)}")


def save_outputs(edges, config):
    """Сохранить текст PlantUML и изображение PNG графа."""
    output_dir = os.path.dirname(config.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    puml_path = config.output_file.replace(".png", ".puml")
    save_plantuml(edges, puml_path)
    render_diagram_png(edges, config.package, config.output_file)
    return puml_path, config.output_file


def main(argv):
    """Запустить приложение: разбор параметров и выполнение этапов."""
    try:
        config = parse_config(argv)
        if config.print_config:
            print_config(config)
            return EXIT_OK
        source = build_source(config)
        if config.direct_only:
            run_direct_mode(source, config)
        else:
            run_full_mode(source, config)
        return EXIT_OK
    except (ConfigError, CargoIndexError, TestRepoError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
