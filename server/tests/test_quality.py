"""Юнит-тесты бизнес-правил проверки сессии (без БД)."""

import numpy as np
import pytest

from app.services.quality import can_transition, evaluate_session
from tests.factories import gaze_arrays

RULES = {"threshold_deg": 0.25, "min_valid_pct": 90.0}


def test_strong_tremor_session_is_checked_with_answer_yes():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    verdict = evaluate_session(100.0, t, xyz, **RULES)
    assert verdict.status == "checked"
    assert verdict.destabilized is True
    assert verdict.reason is None


def test_calm_session_is_checked_with_answer_no():
    t, xyz = gaze_arrays(tremor_deg=0.05)
    verdict = evaluate_session(100.0, t, xyz, **RULES)
    assert verdict.status == "checked"
    assert verdict.destabilized is False


def test_many_lost_samples_means_reject():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    verdict = evaluate_session(80.0, t, xyz, **RULES)
    assert verdict.status == "rejected"
    assert "валидных отсчётов" in verdict.reason
    assert verdict.destabilized is None


def test_valid_pct_exactly_at_minimum_is_accepted():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    assert evaluate_session(90.0, t, xyz, **RULES).status == "checked"


def test_static_gaze_is_rejected_as_tracking_failure():
    t, xyz = gaze_arrays(static=True)
    verdict = evaluate_session(100.0, t, xyz, **RULES)
    assert verdict.status == "rejected"
    assert "неподвижен" in verdict.reason


def test_too_short_recording_is_rejected():
    verdict = evaluate_session(100.0, np.empty(0), np.empty((0, 3)), **RULES)
    assert verdict.status == "rejected"
    assert "мало отсчётов" in verdict.reason


def test_unknown_valid_pct_is_treated_as_zero():
    t, xyz = gaze_arrays(tremor_deg=0.6)
    assert evaluate_session(None, t, xyz, **RULES).status == "rejected"


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("created", "recorded", True),
        ("recorded", "checked", True),
        ("recorded", "rejected", True),
        ("checked", "in_dataset", True),
        ("created", "checked", False),  # нельзя перепрыгнуть шаг
        ("recorded", "in_dataset", False),
        ("checked", "recorded", False),  # назад нельзя
        ("rejected", "in_dataset", False),  # брак в датасет не попадает
        ("in_dataset", "checked", False),
        ("unknown", "checked", False),
    ],
)
def test_lifecycle_transitions(current, target, allowed):
    assert can_transition(current, target) is allowed
