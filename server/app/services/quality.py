"""Бизнес-правила проверки сессии: контроль качества и вердикт «дестабилизация: да/нет».

Чистые функции без обращения к БД: их легко проверять юнит-тестами.
"""

from dataclasses import dataclass

import numpy as np

from app.services.stability import InsufficientDataError, StabilityAssessment, assess

# Допустимые переходы жизненного цикла сессии. «rejected» и «in_dataset» — конечные состояния.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "created": ("recorded",),
    "recorded": ("checked", "rejected"),
    "checked": ("in_dataset",),
    "in_dataset": (),
    "rejected": (),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, ())


@dataclass(frozen=True)
class Verdict:
    """Итог проверки сессии."""

    status: str  # "checked" или "rejected"
    reason: str | None
    assessment: StabilityAssessment | None
    destabilized: bool | None


def evaluate_session(
    valid_pct: float | None,
    t: np.ndarray,
    xyz: np.ndarray,
    *,
    threshold_deg: float,
    min_valid_pct: float,
) -> Verdict:
    """Правило качества: брак -> «rejected», иначе «checked» и ответ «да/нет».

    Брак, если: валидных отсчётов меньше min_valid_pct, данных мало для оценки или взгляд
    абсолютно неподвижен (так выглядит сбой трекинга, а не живой взгляд).
    """
    pct = valid_pct or 0.0
    if pct < min_valid_pct:
        reason = f"валидных отсчётов {pct:.1f}% < {min_valid_pct:.1f}%"
        return Verdict("rejected", reason, None, None)
    try:
        result = assess(t, xyz)
    except InsufficientDataError as exc:
        return Verdict("rejected", str(exc), None, None)
    if result.static:
        return Verdict("rejected", "взгляд неподвижен: похоже на сбой трекинга", result, None)
    return Verdict("checked", None, result, result.is_destabilized(threshold_deg))
