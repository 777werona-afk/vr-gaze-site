"""Юнит-тесты оценки стабильности взгляда (без БД)."""

import numpy as np
import pytest

from app.services.stability import (
    MIN_SAMPLES,
    InsufficientDataError,
    assess,
    gaze_angles,
)
from tests.factories import gaze_arrays

THRESHOLD = 0.25


def test_tremor_rms_matches_amplitude():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    result = assess(t, xyz)
    # синусоида амплитуды A в полосе тремора даёт RMS = A / sqrt(2) = 0,424°
    assert result.tremor_rms_deg == pytest.approx(0.6 / np.sqrt(2), rel=0.1)
    assert result.fs_hz == pytest.approx(72.0, rel=1e-6)
    assert not result.static


def test_strong_tremor_is_destabilized():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    assert assess(t, xyz).is_destabilized(THRESHOLD) is True


def test_calm_gaze_is_not_destabilized():
    t, xyz = gaze_arrays(tremor_deg=0.05)
    result = assess(t, xyz)
    assert result.tremor_rms_deg < THRESHOLD
    assert result.is_destabilized(THRESHOLD) is False


def test_slow_drift_alone_does_not_look_like_tremor():
    t, xyz = gaze_arrays(tremor_deg=0.0, drift_deg=10.0)
    assert assess(t, xyz).tremor_rms_deg < 0.05


def test_tremor_outside_band_is_ignored():
    # 1 Гц — это обычное движение взгляда, а не тремор 4-12 Гц
    t, xyz = gaze_arrays(tremor_deg=1.0, tremor_hz=1.0)
    assert assess(t, xyz).tremor_rms_deg < THRESHOLD


def test_static_signal_is_flagged_and_never_destabilized():
    t, xyz = gaze_arrays(static=True)
    result = assess(t, xyz)
    assert result.static is True
    assert result.is_destabilized(THRESHOLD) is False


def test_jump_is_cut_out_and_does_not_fake_tremor():
    t, xyz = gaze_arrays(tremor_deg=0.05)
    # мгновенный поворот на 90° посреди записи (сбой трекинга), дальше сигнал продолжается
    rotation = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    xyz[len(xyz) // 2 :] = xyz[len(xyz) // 2 :] @ rotation.T
    yaw, pitch, jumps = gaze_angles(xyz)
    assert jumps == 1
    assert assess(t, xyz).tremor_rms_deg < THRESHOLD


def test_too_few_samples_raises():
    t, xyz = gaze_arrays(n=MIN_SAMPLES - 1)
    with pytest.raises(InsufficientDataError):
        assess(t, xyz)


def test_low_sampling_rate_raises():
    t, xyz = gaze_arrays(n=500, fs=8.0)
    with pytest.raises(InsufficientDataError):
        assess(t, xyz)
