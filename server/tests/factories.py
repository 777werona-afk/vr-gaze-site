"""Генераторы тестовых CSV-логов взгляда (формат: timestamp,gaze_x,gaze_y,gaze_z,pupil,openness).

Сигнал: медленный дрейф взгляда (0,3 Гц, несколько градусов) + тремор 6 Гц заданной амплитуды.
RMS тремора в полосе 4-12 Гц для синусоиды с амплитудой A примерно равен A / sqrt(2),
поэтому при пороге 0,25° амплитуда 0,6° даёт «да», а 0,05° — «нет».
"""

import numpy as np

HEADER = "timestamp,gaze_x,gaze_y,gaze_z,pupil,openness"


def gaze_arrays(
    n: int = 1500,
    fs: float = 72.0,
    tremor_deg: float = 0.0,
    tremor_hz: float = 6.0,
    drift_deg: float = 4.0,
    static: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Время (с) и единичные векторы взгляда (N x 3)."""
    t = np.arange(n) / fs
    if static:
        yaw = np.zeros(n)
        pitch = np.zeros(n)
    else:
        drift = drift_deg * np.sin(2 * np.pi * 0.3 * t)
        yaw = drift + tremor_deg * np.sin(2 * np.pi * tremor_hz * t)
        pitch = 0.5 * drift_deg * np.sin(2 * np.pi * 0.2 * t)
    yaw_r, pitch_r = np.radians(yaw), np.radians(pitch)
    xyz = np.column_stack(
        [np.sin(yaw_r) * np.cos(pitch_r), np.sin(pitch_r), np.cos(yaw_r) * np.cos(pitch_r)]
    )
    return t, xyz


def make_csv(n: int = 1500, *, lost: int = 0, duplicates: int = 0, **signal) -> bytes:
    """CSV-лог. lost — сколько отсчётов с нулевым вектором (потеря трекинга),
    duplicates — сколько строк повторяют метку времени уже записанных отсчётов."""
    t, xyz = gaze_arrays(n, **signal)
    lost_idx = set(np.linspace(5, n - 5, lost, dtype=int)) if lost else set()
    lines = [HEADER]
    for i in range(n):
        x, y, z = (0.0, 0.0, 0.0) if i in lost_idx else xyz[i]
        lines.append(f"{t[i]:.6f},{x:.6f},{y:.6f},{z:.6f},3.500,0.950")
    lines.extend(lines[1 + i] for i in range(duplicates))
    return ("\n".join(lines) + "\n").encode("utf-8")
