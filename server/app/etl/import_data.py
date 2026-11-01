"""ETL: импорт CSV-логов взгляда в БД.

Запуск из командной строки (из папки server/):

    python -m app.etl.import_data --source ../data/raw
    python -m app.etl.import_data --source session.csv --participant P-001 --group "Контрольная"
    python -m app.etl.import_data --source session.csv --session-id 5

Этапы: извлечение (чтение CSV) -> валидация и очистка -> преобразование -> загрузка в БД.
Идемпотентность: файл опознаётся по SHA-256 содержимого, повторный запуск пропускает уже
загруженные файлы и не создаёт дубликатов. В лог пишется, сколько строк загружено и сколько
отклонено, с разбивкой по причинам.
"""

import argparse
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, engine
from app.etl.clean import CleanedLog, CsvFormatError, clean_csv
from app.models import GazeSample, GazeSession, Participant, ParticipantGroup
from app.services.errors import ConflictError, DomainError, NotFoundError

logger = logging.getLogger("app.etl")

CHUNK = 5000
DEFAULT_PARTICIPANT = "P-PILOT"
DEFAULT_GROUP = "Пилот"


@dataclass
class FileOutcome:
    file: str
    status: str  # "loaded" | "skipped" | "failed"
    message: str = ""
    session_id: int | None = None
    total_rows: int = 0
    loaded_rows: int = 0
    rejected: dict[str, int] = field(default_factory=dict)


@dataclass
class ImportReport:
    outcomes: list[FileOutcome] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(1 for item in self.outcomes if item.status == status)

    @property
    def loaded(self) -> int:
        return self._count("loaded")

    @property
    def skipped(self) -> int:
        return self._count("skipped")

    @property
    def failed(self) -> int:
        return self._count("failed")

    @property
    def rows_loaded(self) -> int:
        return sum(item.loaded_rows for item in self.outcomes)


def _nullable(value: float) -> float | None:
    return None if np.isnan(value) else float(value)


async def _get_or_create_participant(db: AsyncSession, code: str, group_name: str) -> Participant:
    participant = await db.scalar(select(Participant).where(Participant.code == code))
    if participant is not None:
        return participant
    group = await db.scalar(select(ParticipantGroup).where(ParticipantGroup.name == group_name))
    if group is None:
        group = ParticipantGroup(name=group_name)
        db.add(group)
        await db.flush()
    participant = Participant(code=code, group_id=group.id)
    db.add(participant)
    await db.flush()
    return participant


async def _prepare_session(
    db: AsyncSession, participant_code: str, group_name: str, session_id: int | None
) -> GazeSession:
    """Находит сессию «created» для заполнения данными или создаёт новую."""
    if session_id is None:
        participant = await _get_or_create_participant(db, participant_code, group_name)
        session = GazeSession(participant_id=participant.id)
        db.add(session)
        return session
    session = await db.get(GazeSession, session_id)
    if session is None:
        raise NotFoundError("Сессия не найдена")
    if session.status != "created":
        raise ConflictError(
            "Данные можно загрузить только в сессию со статусом 'created', "
            f"сейчас '{session.status}'"
        )
    return session


async def _load_samples(db: AsyncSession, session_id: int, log: CleanedLog) -> None:
    rows = [
        {
            "session_id": session_id,
            "t_s": float(log.t[i]),
            "x": float(log.xyz[i, 0]),
            "y": float(log.xyz[i, 1]),
            "z": float(log.xyz[i, 2]),
            "pupil": _nullable(log.pupil[i]),
            "openness": _nullable(log.openness[i]),
        }
        for i in range(log.valid_rows)
    ]
    for start in range(0, len(rows), CHUNK):
        await db.execute(insert(GazeSample), rows[start : start + CHUNK])


async def import_bytes(
    db: AsyncSession,
    data: bytes,
    name: str,
    *,
    participant_code: str = DEFAULT_PARTICIPANT,
    group_name: str = DEFAULT_GROUP,
    session_id: int | None = None,
) -> FileOutcome:
    """Импортирует один CSV-файл (уже прочитанный в память)."""
    digest = hashlib.sha256(data).hexdigest()
    existing = await db.scalar(select(GazeSession.id).where(GazeSession.source_sha256 == digest))
    if existing is not None:
        return FileOutcome(name, "skipped", f"файл уже загружен (сессия {existing})", existing)

    try:
        log = clean_csv(data)
    except CsvFormatError as exc:
        return FileOutcome(name, "failed", str(exc))
    if log.valid_rows == 0:
        return FileOutcome(
            name, "failed", "нет ни одного валидного отсчёта", None, log.total_rows, 0, log.rejected
        )

    session = await _prepare_session(db, participant_code, group_name, session_id)
    session.status = "recorded"
    session.source_file = name
    session.source_sha256 = digest
    session.recorded_at = session.recorded_at or datetime.now(UTC)
    session.total_rows = log.total_rows
    session.valid_rows = log.valid_rows
    session.valid_pct = log.valid_pct
    try:
        await db.flush()
        await _load_samples(db, session.id, log)
        await db.commit()
    except IntegrityError:
        # параллельный запуск успел загрузить тот же файл раньше нас
        await db.rollback()
        return FileOutcome(name, "skipped", "файл уже загружен другим процессом")

    return FileOutcome(
        name, "loaded", "", session.id, log.total_rows, log.valid_rows, dict(log.rejected)
    )


async def import_path(
    db: AsyncSession,
    source: Path,
    *,
    participant_code: str = DEFAULT_PARTICIPANT,
    group_name: str = DEFAULT_GROUP,
    session_id: int | None = None,
) -> ImportReport:
    """Импортирует файл или все *.csv из папки и пишет результат каждого файла в лог."""
    if not source.exists():
        raise FileNotFoundError(f"Источник не найден: {source}")
    files = [source] if source.is_file() else sorted(source.rglob("*.csv"))
    if session_id is not None and len(files) != 1:
        raise ValueError("--session-id можно использовать только с одним файлом")

    report = ImportReport()
    for path in files:
        try:
            outcome = await import_bytes(
                db,
                path.read_bytes(),
                path.name,
                participant_code=participant_code,
                group_name=group_name,
                session_id=session_id,
            )
        except DomainError as exc:
            await db.rollback()
            outcome = FileOutcome(path.name, "failed", exc.message)
        report.outcomes.append(outcome)
        _log_outcome(outcome)
    logger.info(
        "Готово: загружено файлов %d (%d строк), пропущено %d, с ошибкой %d",
        report.loaded,
        report.rows_loaded,
        report.skipped,
        report.failed,
    )
    return report


def _log_outcome(outcome: FileOutcome) -> None:
    if outcome.status == "loaded":
        rejected = sum(outcome.rejected.values())
        reasons = "; ".join(f"{reason}: {n}" for reason, n in outcome.rejected.items())
        logger.info(
            "%s: загружено %d из %d строк, отклонено %d%s (сессия %s)",
            outcome.file,
            outcome.loaded_rows,
            outcome.total_rows,
            rejected,
            f" ({reasons})" if reasons else "",
            outcome.session_id,
        )
    elif outcome.status == "skipped":
        logger.info("%s: пропущен, %s", outcome.file, outcome.message)
    else:
        logger.error("%s: ошибка, %s", outcome.file, outcome.message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Импорт CSV-логов взгляда в БД (ETL).")
    parser.add_argument("--source", required=True, type=Path, help="CSV-файл или папка с CSV")
    parser.add_argument("--participant", default=DEFAULT_PARTICIPANT, help="код участника")
    parser.add_argument("--group", default=DEFAULT_GROUP, help="группа для нового участника")
    parser.add_argument("--session-id", type=int, help="заполнить уже созданную сессию (created)")
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        async with SessionLocal() as db:
            report = await import_path(
                db,
                args.source,
                participant_code=args.participant,
                group_name=args.group,
                session_id=args.session_id,
            )
    finally:
        await engine.dispose()
    return 1 if report.failed else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
