"""Этапы «извлечение, валидация, очистка, преобразование» ETL для CSV-логов взгляда.

Формат лога: timestamp, gaze_x, gaze_y, gaze_z, pupil, openness (одна строка — один отсчёт).
Модуль чистый: не знает про БД, поэтому его функции легко тестировать. Всё, что отбрасывается,
считается по причинам, чтобы ETL мог написать в лог, сколько строк отклонено и почему.
"""

import csv
import io
from dataclasses import dataclass, field

import numpy as np

REASON_BAD_FORMAT = "некорректный формат или пропуск значения"
REASON_LOST = "потеря трекинга (нулевой вектор взгляда)"
REASON_DUPLICATE = "дубликат метки времени"

_ZERO_NORM = 1e-6


class CsvFormatError(ValueError):
    """Файл нельзя прочитать как лог взгляда (пустой, нет обязательных колонок)."""


@dataclass
class CleanedLog:
    """Очищенный лог: отсчёты по возрастанию времени, векторы взгляда единичной длины."""

    t: np.ndarray  # секунды от начала записи
    xyz: np.ndarray  # N x 3
    pupil: np.ndarray  # NaN, если колонки нет или значение не прочитано
    openness: np.ndarray
    total_rows: int
    rejected: dict[str, int] = field(default_factory=dict)

    @property
    def valid_rows(self) -> int:
        return int(len(self.t))

    @property
    def valid_pct(self) -> float:
        return 100.0 * self.valid_rows / self.total_rows if self.total_rows else 0.0


def _detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in (",", ";", "\t")}
    return max(counts, key=counts.get) if max(counts.values()) else ","


def _find_columns(header: list[str]) -> dict[str, int]:
    """Сопоставляет названия колонок независимо от регистра, пробелов и точек."""
    found: dict[str, int] = {}
    for idx, raw in enumerate(header):
        name = raw.strip().lower().replace(" ", "_").replace(".", "_")
        if "time" in name or name in ("t", "ts"):
            found.setdefault("t", idx)
        elif name in ("gaze_x", "gazex", "gaze_dir_x", "x"):
            found.setdefault("x", idx)
        elif name in ("gaze_y", "gazey", "gaze_dir_y", "y"):
            found.setdefault("y", idx)
        elif name in ("gaze_z", "gazez", "gaze_dir_z", "z"):
            found.setdefault("z", idx)
        elif "pupil" in name:
            found.setdefault("pupil", idx)
        elif "open" in name:
            found.setdefault("openness", idx)
    missing = [key for key in ("t", "x", "y", "z") if key not in found]
    if missing:
        raise CsvFormatError(f"не найдены колонки {missing}; есть: {header}")
    return found


def _to_float(text: str) -> float:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return float("nan")


def _optional(row: list[str], columns: dict[str, int], key: str) -> float:
    """Необязательная колонка: NaN, если её нет в файле или значение не читается."""
    idx = columns.get(key)
    return _to_float(row[idx]) if idx is not None and len(row) > idx else float("nan")


def _to_seconds(raw: np.ndarray) -> np.ndarray:
    """Приводит метки времени к секундам от начала записи (с, мс, мкс или нс)."""
    steps = np.diff(raw)
    steps = steps[steps > 0]
    median = float(np.median(steps)) if len(steps) else 1.0
    if median > 1e7:
        scale = 1e9
    elif median > 1e4:
        scale = 1e6
    elif median > 1.0:
        scale = 1e3
    else:
        scale = 1.0
    return (raw - raw[0]) / scale


def clean_csv(data: bytes) -> CleanedLog:
    """Читает CSV-лог и возвращает очищенные отсчёты вместе со статистикой отбраковки."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise CsvFormatError("пустой файл")
    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    columns = _find_columns(next(reader))
    need = max(columns[key] for key in ("t", "x", "y", "z")) + 1

    # --- извлечение и валидация формата: строки с нечисловыми значениями отбрасываем
    parsed: list[tuple[float, float, float, float, float, float]] = []
    total = 0
    bad_format = 0
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue  # пустые строки не считаем отсчётами
        total += 1
        if len(row) < need:
            bad_format += 1
            continue
        t, x, y, z = (_to_float(row[columns[key]]) for key in ("t", "x", "y", "z"))
        if not all(np.isfinite(v) for v in (t, x, y, z)):
            bad_format += 1
            continue
        pupil = _optional(row, columns, "pupil")
        openness = _optional(row, columns, "openness")
        parsed.append((t, x, y, z, pupil, openness))

    rejected: dict[str, int] = {}
    if bad_format:
        rejected[REASON_BAD_FORMAT] = bad_format
    empty = np.empty(0)
    if not parsed:
        return CleanedLog(empty, np.empty((0, 3)), empty, empty, total, rejected)

    arr = np.array(parsed, dtype=float)
    t = _to_seconds(arr[:, 0])
    xyz = arr[:, 1:4]
    pupil, openness = arr[:, 4], arr[:, 5]

    # --- очистка: нулевой вектор взгляда — потеря трекинга (например, моргание)
    norm = np.linalg.norm(xyz, axis=1)
    alive = norm > _ZERO_NORM
    lost = int((~alive).sum())
    if lost:
        rejected[REASON_LOST] = lost
    t, xyz, pupil, openness, norm = t[alive], xyz[alive], pupil[alive], openness[alive], norm[alive]

    # --- преобразование: порядок по времени, единичные векторы, без повторов меток времени
    order = np.argsort(t, kind="stable")
    t, xyz, pupil, openness, norm = t[order], xyz[order], pupil[order], openness[order], norm[order]
    if len(t):
        t = t - t[0]  # секунды от самого раннего отсчёта, а не от первой строки файла
    xyz = xyz / norm[:, None]
    keep = np.concatenate([[True], np.diff(t) > 0]) if len(t) else np.zeros(0, dtype=bool)
    duplicates = int((~keep).sum())
    if duplicates:
        rejected[REASON_DUPLICATE] = duplicates
    return CleanedLog(t[keep], xyz[keep], pupil[keep], openness[keep], total, rejected)
