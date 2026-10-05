#!/usr/bin/env python3
"""Конвейер «данные → результат → сайт» (задание P3).

Читает CSV-логи взгляда из data/raw/ (формат: timestamp, gaze_x/y/z, pupil, openness),
считает статистику и метрики тремора, применяет фильтр-стабилизатор (One Euro),
сохраняет таблицы и графики, а также метку версии (хеш коммита, дата сборки,
хеш набора данных). Результат кладётся в docs/, откуда его подхватывает MkDocs.

Кэширование: если входные данные, код и параметры не изменились — пересчёт пропускается.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import signal  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DEMO_DIR = ROOT / "data" / "demo"
GEN_MD = ROOT / "generated"
GEN_IMG = ROOT / "docs" / "assets" / "generated"
RESULTS = ROOT / "results"
CACHE_FILE = RESULTS / ".cache.json"

JUMP_DEG = 30.0  # шаг направления взгляда между соседними кадрами больше этого значения считаем разрывом

PARAMS = {
    "jump_deg": JUMP_DEG,
    "tremor_band_hz": [4.0, 12.0],
    "highpass_hz": 2.0,
    "one_euro": {"mincutoff": 1.0, "beta": 0.001, "dcutoff": 1.0},
    "sweep_beta": [0.0, 0.001, 0.007],
    "script_version": "1.0",
}


# ----------------------------------------------------------------------------- загрузка
def find_columns(df: pd.DataFrame) -> dict[str, str]:
    """Сопоставляет названия колонок независимо от регистра и разделителей."""
    norm = {c: c.strip().lower().replace(" ", "_").replace(".", "_") for c in df.columns}
    inv: dict[str, str] = {}
    for orig, n in norm.items():
        if "time" in n or n in ("t", "ts"):
            inv.setdefault("t", orig)
        elif n in ("gaze_x", "gazex", "gaze_dir_x", "x"):
            inv.setdefault("x", orig)
        elif n in ("gaze_y", "gazey", "gaze_dir_y", "y"):
            inv.setdefault("y", orig)
        elif n in ("gaze_z", "gazez", "gaze_dir_z", "z"):
            inv.setdefault("z", orig)
        elif "pupil" in n:
            inv.setdefault("pupil", orig)
        elif "open" in n:
            inv.setdefault("openness", orig)
    missing = [k for k in ("t", "x", "y", "z") if k not in inv]
    if missing:
        raise ValueError(f"не найдены колонки {missing}; есть: {list(df.columns)}")
    return inv


def to_seconds(raw: pd.Series) -> np.ndarray:
    """Приводит метки времени к секундам (с, мс, мкс, нс или datetime-строки)."""
    if not pd.api.types.is_numeric_dtype(raw):
        dt = pd.to_datetime(raw, errors="coerce")
        return ((dt - dt.iloc[0]).dt.total_seconds()).to_numpy(dtype=float)
    t = raw.to_numpy(dtype=float)
    d = np.diff(t)
    d = d[d > 0]
    m = float(np.median(d)) if len(d) else 1.0
    if m > 1e7:
        scale = 1e9
    elif m > 1e4:
        scale = 1e6
    elif m > 1.0:
        scale = 1e3
    else:
        scale = 1.0
    return (t - t[0]) / scale


def load_session(path: Path) -> dict:
    df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    cols = find_columns(df)
    n_total = len(df)
    t = to_seconds(df[cols["t"]])
    xyz = df[[cols["x"], cols["y"], cols["z"]]].to_numpy(dtype=float)
    pupil = df[cols["pupil"]].to_numpy(dtype=float) if "pupil" in cols else np.full(n_total, np.nan)
    openness = df[cols["openness"]].to_numpy(dtype=float) if "openness" in cols else np.full(n_total, np.nan)

    norm = np.linalg.norm(xyz, axis=1)
    valid = np.isfinite(t) & np.isfinite(norm) & (norm > 1e-6)
    order = np.argsort(t[valid], kind="stable")
    tv, xyzv = t[valid][order], xyz[valid][order]
    xyzv = xyzv / np.linalg.norm(xyzv, axis=1, keepdims=True)
    keep = np.concatenate([[True], np.diff(tv) > 0])  # убираем дубли временных меток
    tv, xyzv = tv[keep], xyzv[keep]

    # Скачки направления взгляда. Между соседними кадрами (~14 мс при 72 Гц) глаза и голова не могут
    # повернуться на десятки градусов, поэтому такой шаг — не движение, а разрыв сигнала (мгновенный
    # поворот сцены или сбой отслеживания). Шаг вырезаем, а сегменты склеиваем: иначе ступенька
    # попадает в спектр и ложно «увеличивает тремор».
    yaw0 = np.arctan2(xyzv[:, 0], xyzv[:, 2])
    pitch0 = np.arctan2(xyzv[:, 1], np.hypot(xyzv[:, 0], xyzv[:, 2]))
    step = np.degrees(np.arccos(np.clip((xyzv[1:] * xyzv[:-1]).sum(axis=1), -1.0, 1.0)))
    jumps = step > JUMP_DEG
    dyaw = (np.diff(yaw0) + np.pi) % (2 * np.pi) - np.pi  # кратчайшая разность углов (переход через ±180°)
    dpitch = np.diff(pitch0)
    dyaw[jumps] = 0.0
    dpitch[jumps] = 0.0
    yaw = np.degrees(yaw0[0] + np.concatenate([[0.0], np.cumsum(dyaw)]))
    pitch = np.degrees(pitch0[0] + np.concatenate([[0.0], np.cumsum(dpitch)]))
    return {
        "name": path.stem,
        "n_total": n_total,
        "n_valid": int(valid.sum()),
        "t": tv,
        "yaw": yaw,
        "pitch": pitch,
        "n_jumps": int(jumps.sum()),
        "pupil_mean": float(np.nanmean(pupil[valid])) if np.isfinite(pupil[valid]).any() else float("nan"),
        "openness_mean": float(np.nanmean(openness[valid])) if np.isfinite(openness[valid]).any() else float("nan"),
    }


# ----------------------------------------------------------------------------- обработка
def resample_uniform(t: np.ndarray, *series: np.ndarray) -> tuple[float, np.ndarray, list[np.ndarray]]:
    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt
    tu = np.arange(t[0], t[-1], dt)
    return fs, tu, [np.interp(tu, t, s) for s in series]


class OneEuro:
    """Фильтр One Euro (Casiez et al., 2012) — адаптивное сглаживание с малой задержкой."""

    def __init__(self, fs: float, mincutoff: float, beta: float, dcutoff: float):
        self.fs, self.mincutoff, self.beta, self.dcutoff = fs, mincutoff, beta, dcutoff

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2 * np.pi * cutoff)
        return 1.0 / (1.0 + tau * self.fs)

    def apply(self, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x)
        out[0] = x[0]
        dx_prev = 0.0
        for i in range(1, len(x)):
            dx = (x[i] - out[i - 1]) * self.fs
            a_d = self._alpha(self.dcutoff)
            dx_hat = a_d * dx + (1 - a_d) * dx_prev
            cutoff = self.mincutoff + self.beta * abs(dx_hat)
            a = self._alpha(cutoff)
            out[i] = a * x[i] + (1 - a) * out[i - 1]
            dx_prev = dx_hat
        return out


def jitter_rms(x: np.ndarray, fs: float, hp: float) -> float:
    """RMS высокочастотной составляющей (град) — оценка дрожания."""
    sos = signal.butter(2, hp, btype="highpass", fs=fs, output="sos")
    return float(np.sqrt(np.mean(signal.sosfiltfilt(sos, x) ** 2)))


def band_fraction(x: np.ndarray, fs: float, lo: float, hi: float) -> tuple[float, float]:
    """Доля мощности в полосе тремора и доминирующая частота в ней."""
    nper = int(min(len(x), max(256, 4 * fs)))
    f, p = signal.welch(signal.detrend(x), fs=fs, nperseg=nper)
    total = p[f >= 0.5].sum()
    band = (f >= lo) & (f <= hi)
    frac = float(p[band].sum() / total) if total > 1e-12 else float("nan")
    # частота пика — только если в полосе есть настоящий локальный максимум спектра
    dom = float("nan")
    if band.any():
        peaks, _ = signal.find_peaks(p[band])
        if len(peaks):
            dom = float(f[band][peaks[np.argmax(p[band][peaks])]])
    return frac, dom


def band_rms(x: np.ndarray, fs: float, lo: float, hi: float) -> float:
    """RMS сигнала в полосе тремора (полосовой фильтр Баттерворта), градусы."""
    sos = signal.butter(2, [lo, min(hi, 0.45 * fs)], btype="bandpass", fs=fs, output="sos")
    return float(np.sqrt(np.mean(signal.sosfiltfilt(sos, x) ** 2)))


def lag_ms(raw: np.ndarray, filt: np.ndarray, fs: float, max_ms: float = 400.0) -> float:
    """Задержка фильтра: сдвиг (мс), при котором выход лучше всего совпадает с задержанным входом."""
    kmax = int(max_ms / 1000 * fs)
    errs = [np.mean((filt[k:] - raw[: len(raw) - k]) ** 2) for k in range(kmax + 1)]
    return float(np.argmin(errs) / fs * 1000)


STATIC_EPS_DEG = 1e-3  # ниже этого уровня сигнал считаем неподвижным (шума нет, оценивать нечего)


def process(sess: dict) -> dict:
    fs, tu, (yaw, pitch) = resample_uniform(sess["t"], sess["yaw"], sess["pitch"])
    lo, hi = PARAMS["tremor_band_hz"]
    hp = PARAMS["highpass_hz"]
    flt = OneEuro(fs, **PARAMS["one_euro"])
    yaw_f, pitch_f = flt.apply(yaw), flt.apply(pitch)

    j_raw = float(np.hypot(jitter_rms(yaw, fs, hp), jitter_rms(pitch, fs, hp)))
    j_flt = float(np.hypot(jitter_rms(yaw_f, fs, hp), jitter_rms(pitch_f, fs, hp)))
    frac_raw, dom = band_fraction(yaw, fs, lo, hi)
    frac_flt, _ = band_fraction(yaw_f, fs, lo, hi)
    tr_raw = float(np.hypot(band_rms(yaw, fs, lo, hi), band_rms(pitch, fs, lo, hi)))
    tr_flt = float(np.hypot(band_rms(yaw_f, fs, lo, hi), band_rms(pitch_f, fs, lo, hi)))
    static = bool(np.ptp(yaw) < STATIC_EPS_DEG and np.ptp(pitch) < STATIC_EPS_DEG)
    speed = np.hypot(np.gradient(yaw, 1 / fs), np.gradient(pitch, 1 / fs))
    sweep = {}
    for b in PARAMS["sweep_beta"]:
        f2 = OneEuro(fs, PARAMS["one_euro"]["mincutoff"], b, PARAMS["one_euro"]["dcutoff"])
        yb, pb = f2.apply(yaw), f2.apply(pitch)
        sweep[b] = (float(np.hypot(band_rms(yb, fs, lo, hi), band_rms(pb, fs, lo, hi))), lag_ms(yaw, yb, fs))
    return {
        "session": sess["name"],
        "rows": sess["n_total"],
        "valid_pct": 100.0 * sess["n_valid"] / sess["n_total"],
        "n_jumps": sess["n_jumps"],
        "duration_s": float(sess["t"][-1] - sess["t"][0]),
        "fs_hz": fs,
        "pupil_mean": sess["pupil_mean"],
        "openness_mean": sess["openness_mean"],
        "speed_median_dps": float(np.median(speed)),
        "jitter_raw_deg": j_raw,
        "jitter_filtered_deg": j_flt,
        "jitter_reduction_pct": float("nan") if static else 100.0 * (1 - j_flt / j_raw),
        "static": static,
        "tremor_rms_raw_deg": tr_raw,
        "tremor_rms_filtered_deg": tr_flt,
        "tremor_reduction_pct": float("nan") if static else 100.0 * (1 - tr_flt / tr_raw),
        "tremor_band_frac_raw": frac_raw,
        "tremor_band_frac_filtered": frac_flt,
        "tremor_peak_hz": dom,
        "lag_ms": lag_ms(yaw, yaw_f, fs),
        "_sweep": sweep,
        "_arrays": (tu, yaw, pitch, yaw_f, pitch_f, fs),
    }


# ----------------------------------------------------------------------------- вывод
def make_figures(results: list[dict]) -> None:
    GEN_IMG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    c_raw, c_flt = "#4C78A8", "#E45756"

    # 1) тремор (полоса 4–12 Гц) до/после по сессиям
    names = [short_name(r["session"]) for r in results]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(x - 0.2, [r["tremor_rms_raw_deg"] for r in results], 0.4, label="без фильтра", color=c_raw)
    ax.bar(x + 0.2, [r["tremor_rms_filtered_deg"] for r in results], 0.4, label="One Euro", color=c_flt)
    ax.set_xticks(x, [n.replace("_", "\n", 1) for n in names], fontsize=8)
    ax.set_ylabel("RMS в полосе 4–12 Гц, °")
    ax.set_title("Колебания взгляда в полосе тремора по сессиям")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(GEN_IMG / "jitter_by_session.png", dpi=140)
    plt.close(fig)

    # 2) фрагмент траектории и спектр для самой длинной сессии с движением
    moving = [r for r in results if not r["static"]] or results
    ref = max(moving, key=lambda r: r["duration_s"])
    tu, yaw, _, yaw_f, _, fs = ref["_arrays"]
    n = min(len(tu), int(10 * fs))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    axes[0].plot(tu[:n] - tu[0], yaw[:n], color=c_raw, lw=1, label="без фильтра")
    axes[0].plot(tu[:n] - tu[0], yaw_f[:n], color=c_flt, lw=1.2, label="One Euro")
    axes[0].set(xlabel="время, с", ylabel="горизонт. угол взгляда, °", title=f"Траектория, {short_name(ref['session'])}")
    axes[0].legend(frameon=False)
    nper = int(min(len(yaw), max(256, 4 * fs)))
    for arr, col, lab in ((yaw, c_raw, "без фильтра"), (yaw_f, c_flt, "One Euro")):
        f, p = signal.welch(signal.detrend(arr), fs=fs, nperseg=nper)
        axes[1].semilogy(f, p, color=col, label=lab)
    lo, hi = PARAMS["tremor_band_hz"]
    axes[1].axvspan(lo, hi, color="#999", alpha=0.15, label="полоса тремора")
    axes[1].set(xlabel="частота, Гц", ylabel="PSD, °²/Гц", title="Спектр мощности", xlim=(0, min(30, fs / 2)))
    axes[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(GEN_IMG / "trace_and_psd.png", dpi=140)
    plt.close(fig)


def short_name(name: str) -> str:
    return name.replace("gaze_session_", "")


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    rows = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False))
    return head + rows + "\n"


def write_outputs(results: list[dict], meta: dict) -> pd.DataFrame:
    RESULTS.mkdir(exist_ok=True)
    GEN_MD.mkdir(parents=True, exist_ok=True)
    rows = [{k: v for k, v in r.items() if k not in ("_arrays", "_sweep")} for r in results]
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "summary.csv", index=False, float_format="%.5f")

    def fmt(v, nd: int = 3) -> str:
        return "—" if pd.isna(v) else f"{v:.{nd}f}".replace(".", ",")

    mv = df[~df["static"]]  # средние считаем только по сессиям, где взгляд двигался
    pretty = pd.DataFrame(
        {
            "Сессия": df["session"].map(short_name) + df["static"].map({True: " (статичная)", False: ""}),
            "Строк": df["rows"],
            "Длит., с": df["duration_s"].map(lambda v: fmt(v, 1)),
            "Частота, Гц": df["fs_hz"].map(lambda v: fmt(v, 1)),
            "Разрывов": df["n_jumps"],
            "Скорость, °/с": df["speed_median_dps"].map(lambda v: fmt(v, 1)),
            "Тремор до, °": df["tremor_rms_raw_deg"].map(fmt),
            "Тремор после, °": df["tremor_rms_filtered_deg"].map(fmt),
            "Снижение, %": df["tremor_reduction_pct"].map(lambda v: fmt(v, 1)),
            "Джиттер >2 Гц до, °": df["jitter_raw_deg"].map(fmt),
            "Джиттер после, °": df["jitter_filtered_deg"].map(fmt),
            "Пик, Гц": df["tremor_peak_hz"].map(lambda v: fmt(v, 1)),
        }
    )
    total = {
        "Сессия": f"**Итого / среднее по {len(mv)} сессиям с движением**",
        "Строк": int(df["rows"].sum()),
        "Длит., с": fmt(df["duration_s"].sum(), 1),
        "Частота, Гц": fmt(mv["fs_hz"].mean(), 1),
        "Разрывов": int(df["n_jumps"].sum()),
        "Скорость, °/с": fmt(mv["speed_median_dps"].mean(), 1),
        "Тремор до, °": fmt(mv["tremor_rms_raw_deg"].mean()),
        "Тремор после, °": fmt(mv["tremor_rms_filtered_deg"].mean()),
        "Снижение, %": fmt(mv["tremor_reduction_pct"].mean(), 1),
        "Джиттер >2 Гц до, °": fmt(mv["jitter_raw_deg"].mean()),
        "Джиттер после, °": fmt(mv["jitter_filtered_deg"].mean()),
        "Пик, Гц": "—",
    }
    pretty = pd.concat([pretty, pd.DataFrame([total])], ignore_index=True)
    (GEN_MD / "summary_table.md").write_text(md_table(pretty), encoding="utf-8")

    # чувствительность стабилизатора к параметру beta (только сессии с движением)
    mv_res = [r for r in results if not r["static"]]
    sw_rows = []
    for b in PARAMS["sweep_beta"]:
        red = [100 * (1 - r["_sweep"][b][0] / r["tremor_rms_raw_deg"]) for r in mv_res]
        lag = [r["_sweep"][b][1] for r in mv_res]
        sw_rows.append(
            {
                "beta": fmt(b).replace(",000", ",0") if b else "0",
                "Среднее снижение тремора, %": fmt(float(np.mean(red)), 1),
                "Сессий со снижением": f"{sum(v > 0 for v in red)} из {len(red)}",
                "Средняя задержка, мс": fmt(float(np.mean(lag)), 0),
            }
        )
    (GEN_MD / "sweep_table.md").write_text(md_table(pd.DataFrame(sw_rows)), encoding="utf-8")

    banner = ""
    if meta["synthetic"]:
        banner = (
            '!!! danger "ДЕМО-ДАННЫЕ"\n'
            "    В `data/raw/` нет файлов, поэтому конвейер отработал на **синтетических** данных. "
            "Это не результаты эксперимента. Положите настоящие CSV в `data/raw/` и перезапустите сборку.\n\n"
        )
    stamp = (
        banner
        + "| Параметр | Значение |\n|---|---|\n"
        + f"| Коммит | `{meta['commit']}` |\n"
        + f"| Дата сборки (UTC) | {meta['built_at']} |\n"
        + f"| Версия набора данных | {meta['dataset_version']} |\n"
        + f"| SHA-256 набора данных | `{meta['dataset_sha256'][:16]}…` |\n"
        + f"| Файлов / строк | {meta['n_files']} / {meta['n_rows']} |\n"
        + f"| Версия скрипта | {PARAMS['script_version']} |\n"
    )
    (GEN_MD / "version_stamp.md").write_text(stamp, encoding="utf-8")
    (RESULTS / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return df


# ----------------------------------------------------------------------------- служебное
def sha256_files(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except Exception:
        return "no-git"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="игнорировать кэш")
    args = ap.parse_args()
    t0 = time.perf_counter()

    files = sorted(RAW_DIR.rglob("*.csv"))
    synthetic = False
    if not files:
        print("[warn] data/raw/ пуст — использую СИНТЕТИЧЕСКИЕ демо-данные", file=sys.stderr)
        if not list(DEMO_DIR.glob("*.csv")):
            subprocess.run([sys.executable, str(ROOT / "scripts" / "make_demo_data.py")], check=True)
        files = sorted(DEMO_DIR.glob("*.csv"))
        synthetic = True

    ds_hash = sha256_files(files)
    key = hashlib.sha256(
        (ds_hash + hashlib.sha256((ROOT / "scripts" / "analyze.py").read_bytes()).hexdigest() + json.dumps(PARAMS, sort_keys=True)).encode()
    ).hexdigest()
    outputs_ok = (GEN_MD / "summary_table.md").exists() and (GEN_IMG / "trace_and_psd.png").exists()
    if not args.force and outputs_ok and CACHE_FILE.exists():
        if json.loads(CACHE_FILE.read_text()).get("key") == key:
            # метку версии обновляем всегда (коммит/дата), тяжёлый расчёт — нет
            meta = json.loads((RESULTS / "meta.json").read_text())
            meta.update(commit=git_commit(), built_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            stamp_src = (GEN_MD / "version_stamp.md").read_text(encoding="utf-8")
            if meta.get("commit") is not None:
                df_rows = len(pd.read_csv(RESULTS / "summary.csv"))
                write_stamp_only(meta, stamp_src, df_rows)
            print(f"[cache] входные данные не менялись — пересчёт пропущен ({time.perf_counter() - t0:.2f} с)")
            return 0

    results, errors = [], []
    for f in files:
        try:
            results.append(process(load_session(f)))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {e}")
            print(f"[error] {f.name}: {e}", file=sys.stderr)
    if not results:
        print("[fatal] ни один файл не удалось обработать", file=sys.stderr)
        return 1

    meta = {
        "commit": git_commit(),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_version": (ROOT / "data" / "DATASET_VERSION").read_text().strip()
        if (ROOT / "data" / "DATASET_VERSION").exists()
        else "не указана",
        "dataset_sha256": ds_hash,
        "n_files": len(results),
        "n_rows": int(sum(r["rows"] for r in results)),
        "synthetic": synthetic,
        "errors": errors,
    }
    make_figures(results)
    write_outputs(results, meta)
    CACHE_FILE.write_text(json.dumps({"key": key}))
    print(f"[ok] обработано сессий: {len(results)}, строк: {meta['n_rows']}, время {time.perf_counter() - t0:.2f} с")
    return 0


def write_stamp_only(meta: dict, old_stamp: str, _rows: int) -> None:
    """Обновляет только коммит и дату в уже сгенерированной метке версии."""
    lines = []
    for ln in old_stamp.splitlines():
        if ln.startswith("| Коммит"):
            ln = f"| Коммит | `{meta['commit']}` |"
        elif ln.startswith("| Дата сборки"):
            ln = f"| Дата сборки (UTC) | {meta['built_at']} |"
        lines.append(ln)
    (GEN_MD / "version_stamp.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
