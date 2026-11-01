"""Юнит-тесты очистки CSV-логов взгляда (без БД)."""

import numpy as np
import pytest

from app.etl.clean import (
    REASON_BAD_FORMAT,
    REASON_DUPLICATE,
    REASON_LOST,
    CsvFormatError,
    clean_csv,
)
from tests.factories import make_csv

HEADER = "timestamp,gaze_x,gaze_y,gaze_z,pupil,openness"


def test_clean_reports_every_rejection_reason():
    log = clean_csv(make_csv(300, lost=6, duplicates=4))
    assert log.total_rows == 304
    assert log.rejected[REASON_LOST] == 6
    assert log.rejected[REASON_DUPLICATE] == 4
    assert log.valid_rows == 294
    assert log.valid_pct == pytest.approx(100 * 294 / 304)
    assert np.all(np.diff(log.t) > 0)
    assert np.allclose(np.linalg.norm(log.xyz, axis=1), 1.0)


def test_bad_rows_are_rejected_not_fatal():
    text = f"{HEADER}\n0.00,0,0,1,3,1\nabc,0,0,1,3,1\n0.02,,0,1,3,1\n0.03,0,0\n0.04,0,0,1,3,1\n"
    log = clean_csv(text.encode())
    assert log.total_rows == 5
    assert log.rejected == {REASON_BAD_FORMAT: 3}
    assert log.valid_rows == 2


def test_semicolon_delimiter_and_decimal_comma():
    text = "timestamp;gaze_x;gaze_y;gaze_z\n0,00;0,0;0,0;1,0\n0,02;0,0;0,0;1,0\n"
    log = clean_csv(text.encode())
    assert log.valid_rows == 2
    assert log.t[1] == pytest.approx(0.02)
    assert np.isnan(log.pupil).all()  # необязательной колонки нет


def test_unsorted_timestamps_are_sorted():
    text = f"{HEADER}\n0.04,0,0,1,3,1\n0.00,0,0,1,3,1\n0.02,0,0,1,3,1\n"
    log = clean_csv(text.encode())
    assert list(log.t) == pytest.approx([0.0, 0.02, 0.04])


def test_millisecond_timestamps_are_converted_to_seconds():
    text = f"{HEADER}\n1000,0,0,1,3,1\n1014,0,0,1,3,1\n1028,0,0,1,3,1\n"
    log = clean_csv(text.encode())
    assert list(log.t) == pytest.approx([0.0, 0.014, 0.028])


def test_utf8_bom_and_column_name_variants():
    text = "﻿Time,Gaze X,Gaze.Y,gaze_z,Pupil Size,Eye Openness\n0.0,0,0,2,3.5,0.9\n"
    log = clean_csv(text.encode("utf-8"))
    assert log.valid_rows == 1
    assert log.xyz[0] == pytest.approx([0.0, 0.0, 1.0])  # вектор нормирован
    assert log.pupil[0] == pytest.approx(3.5)
    assert log.openness[0] == pytest.approx(0.9)


def test_missing_required_columns_raises():
    with pytest.raises(CsvFormatError, match="не найдены колонки"):
        clean_csv(b"timestamp,gaze_x\n0,1\n")


@pytest.mark.parametrize("data", [b"", b"\n\n"])
def test_empty_file_raises(data):
    with pytest.raises(CsvFormatError, match="пустой"):
        clean_csv(data)


def test_file_with_only_bad_rows_gives_empty_log():
    log = clean_csv(f"{HEADER}\nx,y,z,w,1,1\n".encode())
    assert log.valid_rows == 0
    assert log.valid_pct == 0.0
    assert log.rejected == {REASON_BAD_FORMAT: 1}
