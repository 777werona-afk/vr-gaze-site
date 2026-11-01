"""Интеграционные тесты ETL и seed: загрузка в PostgreSQL, идемпотентность, лог."""

import logging

import pytest
from sqlalchemy import func, select

from app.etl.clean import REASON_DUPLICATE, REASON_LOST
from app.etl.import_data import build_parser, import_bytes, import_path
from app.models import Exhibit, GazeSample, GazeSession, Participant, ParticipantGroup
from app.seed import EXHIBITS, GROUPS, PARTICIPANTS, seed
from app.services.errors import ConflictError, NotFoundError
from tests.factories import HEADER, make_csv


async def count(db, model):
    return await db.scalar(select(func.count()).select_from(model))


async def test_import_loads_samples_and_statistics(db):
    outcome = await import_bytes(db, make_csv(300, lost=6, duplicates=4), "pilot.csv")

    assert outcome.status == "loaded"
    assert (outcome.total_rows, outcome.loaded_rows) == (304, 294)
    assert outcome.rejected == {REASON_LOST: 6, REASON_DUPLICATE: 4}

    session = await db.get(GazeSession, outcome.session_id)
    assert session.status == "recorded"
    assert (session.total_rows, session.valid_rows) == (304, 294)
    assert session.valid_pct == pytest.approx(100 * 294 / 304)
    assert session.source_file == "pilot.csv"
    assert len(session.source_sha256) == 64
    assert await count(db, GazeSample) == 294

    # участник и группа по умолчанию созданы автоматически
    assert await db.scalar(select(Participant.code)) == "P-PILOT"
    assert await db.scalar(select(ParticipantGroup.name)) == "Пилот"


async def test_import_is_idempotent(db):
    data = make_csv(200)
    first = await import_bytes(db, data, "a.csv")
    second = await import_bytes(db, data, "renamed.csv")  # то же содержимое под другим именем

    assert first.status == "loaded"
    assert second.status == "skipped"
    assert second.session_id == first.session_id
    assert await count(db, GazeSession) == 1
    assert await count(db, GazeSample) == 200


async def test_import_failures_do_not_create_sessions(db):
    no_columns = await import_bytes(db, b"a,b\n1,2\n", "bad.csv")
    assert no_columns.status == "failed"
    assert "не найдены колонки" in no_columns.message

    no_valid_rows = await import_bytes(db, f"{HEADER}\nx,y,z,w,1,1\n".encode(), "junk.csv")
    assert no_valid_rows.status == "failed"
    assert "нет ни одного валидного отсчёта" in no_valid_rows.message
    assert no_valid_rows.total_rows == 1

    assert await count(db, GazeSession) == 0


async def test_import_into_existing_session_requires_status_created(db):
    first = await import_bytes(db, make_csv(200), "a.csv")  # сессия уже recorded

    with pytest.raises(ConflictError):
        await import_bytes(db, make_csv(210), "b.csv", session_id=first.session_id)
    with pytest.raises(NotFoundError):
        await import_bytes(db, make_csv(220), "c.csv", session_id=9999)


async def test_import_directory_logs_results_and_is_repeatable(db, tmp_path, caplog):
    (tmp_path / "s1.csv").write_bytes(make_csv(200))
    (tmp_path / "s2.csv").write_bytes(make_csv(210, lost=3))
    (tmp_path / "notes.txt").write_text("это не CSV")

    with caplog.at_level(logging.INFO, logger="app.etl"):
        report = await import_path(db, tmp_path)
        again = await import_path(db, tmp_path)

    assert (report.loaded, report.skipped, report.failed) == (2, 0, 0)
    assert report.rows_loaded == 200 + 207
    assert (again.loaded, again.skipped, again.failed) == (0, 2, 0)
    assert await count(db, GazeSession) == 2
    assert "загружено 207 из 210 строк" in caplog.text
    assert "потеря трекинга" in caplog.text
    assert "пропущен" in caplog.text


async def test_import_path_errors(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        await import_path(db, tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="session-id"):
        await import_path(db, tmp_path, session_id=1)  # в пустой папке нет ровно одного файла


async def test_domain_error_is_reported_as_failed_file(db, tmp_path):
    source = tmp_path / "s.csv"
    source.write_bytes(make_csv(200))

    report = await import_path(db, source, session_id=9999)

    assert report.failed == 1
    assert "не найдена" in report.outcomes[0].message


def test_cli_arguments():
    args = build_parser().parse_args(["--source", "data/raw", "--session-id", "3"])
    assert str(args.source) == "data/raw"
    assert args.session_id == 3
    assert args.participant == "P-PILOT"


async def test_seed_is_idempotent(db):
    await seed(db)
    await seed(db)

    assert await count(db, ParticipantGroup) == len(GROUPS)
    assert await count(db, Participant) == len(PARTICIPANTS)
    assert await count(db, Exhibit) == len(EXHIBITS)
