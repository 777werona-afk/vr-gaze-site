#!/usr/bin/env python3
"""Генератор СИНТЕТИЧЕСКИХ демо-данных в формате пилотной записи.

Нужен только чтобы конвейер собирался на чистом клоне, пока в data/raw/
нет настоящего датасета. Это НЕ результаты эксперимента: страница сайта
помечает такие данные баннером «ДЕМО-ДАННЫЕ».

Формат: timestamp,gaze_x,gaze_y,gaze_z,pupil,openness
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def make_session(rng: np.random.Generator, n: int, fs: float, tremor_amp_deg: float) -> pd.DataFrame:
    t = np.arange(n) / fs
    # медленная «осмысленная» траектория взгляда: ступенчатые фиксации со сглаженными саккадами
    steps = rng.normal(0, 4.0, size=(n // 120 + 2, 2)).cumsum(axis=0)
    idx = np.minimum((t * fs / 120).astype(int), len(steps) - 1)
    base = steps[idx]
    kernel = np.ones(15) / 15
    base = np.column_stack([np.convolve(base[:, k], kernel, mode="same") for k in range(2)])
    # физиологический тремор 5-8 Гц + шум датчика
    f_tr = rng.uniform(5.0, 8.0)
    phase = rng.uniform(0, 2 * np.pi, size=2)
    tremor = tremor_amp_deg * np.column_stack(
        [np.sin(2 * np.pi * f_tr * t + phase[0]), np.sin(2 * np.pi * f_tr * t + phase[1])]
    )
    noise = rng.normal(0, 0.05, size=(n, 2))
    yaw, pitch = (base + tremor + noise).T
    yaw_r, pitch_r = np.radians(yaw), np.radians(pitch)
    x = np.sin(yaw_r) * np.cos(pitch_r)
    y = np.sin(pitch_r)
    z = np.cos(yaw_r) * np.cos(pitch_r)
    pupil = 3.5 + 0.3 * np.sin(2 * np.pi * 0.1 * t) + rng.normal(0, 0.03, n)
    openness = np.clip(0.92 + rng.normal(0, 0.03, n), 0, 1)
    # короткие потери трекинга (моргания): нулевой вектор взгляда
    for _ in range(max(1, n // 700)):
        s = rng.integers(0, n - 8)
        x[s : s + 6] = y[s : s + 6] = z[s : s + 6] = 0.0
        openness[s : s + 6] = 0.0
    return pd.DataFrame(
        {"timestamp": t, "gaze_x": x, "gaze_y": y, "gaze_z": z, "pupil": pupil, "openness": openness}
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo")
    ap.add_argument("--sessions", type=int, default=8)
    ap.add_argument("--rows", type=int, default=1890)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    for i in range(1, args.sessions + 1):
        df = make_session(rng, args.rows, fs=90.0, tremor_amp_deg=rng.uniform(0.15, 0.35))
        df.to_csv(out / f"demo_session_{i:02d}.csv", index=False, float_format="%.6f")
    print(f"[demo] записано {args.sessions} синтетических сессий в {out}/")


if __name__ == "__main__":
    main()
