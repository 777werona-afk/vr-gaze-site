"""Оценка стабильности взгляда: «есть дестабилизация — да или нет».

Показатель — RMS колебаний взгляда в полосе физиологического тремора 4-12 Гц (градусы).
Расчёт повторяет scripts/analyze.py (сайт с результатами), поэтому цифры в API и на сайте
совпадают. Модуль не зависит от БД и веб-слоя: на вход массивы времени и единичных
векторов взгляда, на выход число и решение «да/нет».
"""

from dataclasses import dataclass

import numpy as np
from scipy import signal

TREMOR_BAND_HZ = (4.0, 12.0)
# Шаг направления взгляда между соседними отсчётами больше этого значения — не движение, а
# разрыв сигнала (сбой трекинга, поворот сцены). Такие шаги вырезаются, иначе ступенька
# в спектре даёт ложный «тремор».
JUMP_DEG = 30.0
# Если взгляд сдвинулся меньше этого значения за всю запись, сигнал считается неподвижным.
STATIC_EPS_DEG = 1e-3
MIN_SAMPLES = 64


class InsufficientDataError(ValueError):
    """Из такой записи нельзя оценить стабильность (слишком мало или неподходящие данные)."""


@dataclass(frozen=True)
class StabilityAssessment:
    fs_hz: float
    duration_s: float
    n_jumps: int
    static: bool
    tremor_rms_deg: float

    def is_destabilized(self, threshold_deg: float) -> bool:
        """«Да», если взгляд двигался и колебания в полосе тремора не меньше порога."""
        return (not self.static) and self.tremor_rms_deg >= threshold_deg


def gaze_angles(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Единичные векторы взгляда -> горизонтальный и вертикальный углы (градусы).

    Скачки больше JUMP_DEG вырезаются, сегменты склеиваются. Возвращает (yaw, pitch, n_jumps).
    """
    yaw0 = np.arctan2(xyz[:, 0], xyz[:, 2])
    pitch0 = np.arctan2(xyz[:, 1], np.hypot(xyz[:, 0], xyz[:, 2]))
    step = np.degrees(np.arccos(np.clip((xyz[1:] * xyz[:-1]).sum(axis=1), -1.0, 1.0)))
    jumps = step > JUMP_DEG
    # кратчайшая разность углов (корректный переход через ±180°)
    dyaw = (np.diff(yaw0) + np.pi) % (2 * np.pi) - np.pi
    dpitch = np.diff(pitch0)
    dyaw[jumps] = 0.0
    dpitch[jumps] = 0.0
    yaw = np.degrees(yaw0[0] + np.concatenate([[0.0], np.cumsum(dyaw)]))
    pitch = np.degrees(pitch0[0] + np.concatenate([[0.0], np.cumsum(dpitch)]))
    return yaw, pitch, int(jumps.sum())


def band_rms(x: np.ndarray, fs: float, lo: float, hi: float) -> float:
    """RMS сигнала в полосе [lo, hi] Гц (полосовой фильтр Баттерворта, без сдвига фазы)."""
    sos = signal.butter(2, [lo, min(hi, 0.45 * fs)], btype="bandpass", fs=fs, output="sos")
    return float(np.sqrt(np.mean(signal.sosfiltfilt(sos, x) ** 2)))


def assess(t: np.ndarray, xyz: np.ndarray) -> StabilityAssessment:
    """Считает метрики стабильности по очищенным отсчётам.

    t — время в секундах по возрастанию, xyz — единичные векторы взгляда (N x 3).
    """
    t = np.asarray(t, dtype=float)
    xyz = np.asarray(xyz, dtype=float)
    if len(t) < MIN_SAMPLES:
        raise InsufficientDataError(f"слишком мало отсчётов: {len(t)} < {MIN_SAMPLES}")

    yaw, pitch, n_jumps = gaze_angles(xyz)
    dt = float(np.median(np.diff(t)))
    if not dt > 0:
        raise InsufficientDataError("не удалось определить частоту дискретизации")
    fs = 1.0 / dt
    lo, hi = TREMOR_BAND_HZ
    if min(hi, 0.45 * fs) <= lo * 1.05:
        raise InsufficientDataError(f"частота дискретизации {fs:.1f} Гц слишком мала для 4-12 Гц")

    # равномерная сетка времени: фильтр и спектр требуют постоянного шага
    tu = np.arange(t[0], t[-1], dt)
    if len(tu) < MIN_SAMPLES:
        raise InsufficientDataError(f"слишком короткая запись: {len(tu)} отсчётов")
    yaw_u = np.interp(tu, t, yaw)
    pitch_u = np.interp(tu, t, pitch)

    static = bool(np.ptp(yaw_u) < STATIC_EPS_DEG and np.ptp(pitch_u) < STATIC_EPS_DEG)
    tremor = float(np.hypot(band_rms(yaw_u, fs, lo, hi), band_rms(pitch_u, fs, lo, hi)))
    return StabilityAssessment(
        fs_hz=fs,
        duration_s=float(t[-1] - t[0]),
        n_jumps=n_jumps,
        static=static,
        tremor_rms_deg=tremor,
    )
