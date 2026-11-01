"""Интеграционные тесты API VR-музея на реальной PostgreSQL (включая негативные сценарии)."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config import settings
from app.etl.import_data import import_bytes
from app.models import ExhibitView, GazeSample
from tests.factories import make_csv

# ---------------------------------------------------------------- помощники и фикстуры


async def create_group(client, name="Нарушения моторики", **extra):
    resp = await client.post("/groups", json={"name": name, **extra})
    assert resp.status_code == 201
    return resp.json()


async def create_participant(client, group, code="P-001"):
    resp = await client.post("/participants", json={"code": code, "group_id": group["id"]})
    assert resp.status_code == 201
    return resp.json()


async def create_exhibit(client, title="Картина «Утро»", dwell_threshold_ms=1000):
    payload = {"title": title, "dwell_threshold_ms": dwell_threshold_ms}
    resp = await client.post("/exhibits", json=payload)
    assert resp.status_code == 201
    return resp.json()


async def recorded_session(client, db, participant, **csv_args):
    """Создаёт сессию через API и «записывает» в неё данные ETL (created -> recorded)."""
    resp = await client.post("/sessions", json={"participant_id": participant["id"]})
    assert resp.status_code == 201
    session_id = resp.json()["id"]
    outcome = await import_bytes(db, make_csv(**csv_args), "test.csv", session_id=session_id)
    assert outcome.status == "loaded"
    return session_id


async def checked_session(client, db, participant, **csv_args):
    session_id = await recorded_session(client, db, participant, **csv_args)
    resp = await client.post(f"/sessions/{session_id}/check")
    assert resp.status_code == 200
    return resp.json()


@pytest_asyncio.fixture
async def group(client):
    return await create_group(client)


@pytest_asyncio.fixture
async def participant(client, group):
    return await create_participant(client, group)


@pytest_asyncio.fixture
async def exhibit(client):
    return await create_exhibit(client)


# ---------------------------------------------------------------- группы и участники


async def test_group_create_list_and_duplicate(client, group):
    assert group["is_control"] is False
    assert (await client.get("/groups")).json()[0]["name"] == "Нарушения моторики"

    dup = await client.post("/groups", json={"name": "Нарушения моторики"})
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"


async def test_participant_errors(client, group, participant):
    unknown_group = await client.post("/participants", json={"code": "P-9", "group_id": 999})
    assert unknown_group.status_code == 404

    dup = await client.post("/participants", json={"code": "P-001", "group_id": group["id"]})
    assert dup.status_code == 409

    empty = await client.post("/participants", json={"code": "", "group_id": group["id"]})
    assert empty.status_code == 422
    assert empty.json()["code"] == "validation_error"

    assert (await client.get("/participants/999")).status_code == 404


async def test_participant_list_filter_sort_and_pagination(client, group):
    other = await create_group(client, "Контрольная", is_control=True)
    for code in ("P-002", "P-001", "P-003"):
        await create_participant(client, group, code)
    await create_participant(client, other, "C-001")

    in_group = await client.get("/participants", params={"group_id": group["id"], "sort": "code"})
    assert [p["code"] for p in in_group.json()] == ["P-001", "P-002", "P-003"]

    desc = await client.get("/participants", params={"sort": "-code", "limit": 2, "offset": 1})
    # по убыванию: P-003, P-002, P-001, C-001; пропускаем первого и берём двух
    assert [p["code"] for p in desc.json()] == ["P-002", "P-001"]

    assert (await client.get("/participants", params={"sort": "bogus"})).status_code == 422
    assert (await client.get("/participants", params={"limit": 0})).status_code == 422


async def test_participant_update(client, group, participant):
    other = await create_participant(client, group, "P-002")

    ok = await client.patch(f"/participants/{participant['id']}", json={"code": "P-100"})
    assert ok.status_code == 200
    assert ok.json()["code"] == "P-100"

    clash = await client.patch(f"/participants/{participant['id']}", json={"code": other["code"]})
    assert clash.status_code == 409

    bad_group = await client.patch(f"/participants/{participant['id']}", json={"group_id": 999})
    assert bad_group.status_code == 404

    null_code = await client.patch(f"/participants/{participant['id']}", json={"code": None})
    assert null_code.status_code == 422

    assert (await client.patch("/participants/999", json={"code": "X"})).status_code == 404


async def test_participant_with_sessions_cannot_be_deleted(client, participant):
    session = (await client.post("/sessions", json={"participant_id": participant["id"]})).json()

    blocked = await client.delete(f"/participants/{participant['id']}")
    assert blocked.status_code == 409

    assert (await client.delete(f"/sessions/{session['id']}")).status_code == 204
    assert (await client.delete(f"/participants/{participant['id']}")).status_code == 204
    assert (await client.get(f"/participants/{participant['id']}")).status_code == 404
    assert (await client.delete("/participants/999")).status_code == 404


# ---------------------------------------------------------------- сессии: жизненный цикл


async def test_session_create_requires_existing_participant(client):
    resp = await client.post("/sessions", json={"participant_id": 999})
    assert resp.status_code == 404


async def test_session_lifecycle_to_dataset(client, db, participant):
    created = (await client.post("/sessions", json={"participant_id": participant["id"]})).json()
    session_id = created["id"]
    assert created["status"] == "created"
    assert created["destabilized"] is None

    # created -> recorded: данные загружает ETL
    await import_bytes(db, make_csv(tremor_deg=0.6), "s.csv", session_id=session_id)
    recorded = (await client.get(f"/sessions/{session_id}")).json()
    assert recorded["status"] == "recorded"
    assert recorded["valid_pct"] == pytest.approx(100.0)

    # recorded -> checked: контроль качества и ответ «да/нет»
    checked = await client.post(f"/sessions/{session_id}/check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["status"] == "checked"
    assert body["destabilized"] is True
    assert body["tremor_rms_deg"] >= settings.tremor_threshold_deg

    stability = (await client.get(f"/sessions/{session_id}/stability")).json()
    assert stability["verdict"] == "да"
    assert stability["threshold_deg"] == settings.tremor_threshold_deg

    # checked -> in_dataset
    published = await client.post(f"/sessions/{session_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "in_dataset"

    # повторная публикация и повторная проверка невозможны
    assert (await client.post(f"/sessions/{session_id}/publish")).status_code == 409
    assert (await client.post(f"/sessions/{session_id}/check")).status_code == 409


async def test_calm_session_gets_answer_no(client, db, participant):
    body = await checked_session(client, db, participant, tremor_deg=0.05)
    assert body["status"] == "checked"
    assert body["destabilized"] is False
    verdict = (await client.get(f"/sessions/{body['id']}/stability")).json()["verdict"]
    assert verdict == "нет"


async def test_lifecycle_steps_cannot_be_skipped(client, db, participant):
    created = (await client.post("/sessions", json={"participant_id": participant["id"]})).json()
    assert (await client.post(f"/sessions/{created['id']}/check")).status_code == 409
    assert (await client.post(f"/sessions/{created['id']}/publish")).status_code == 409
    assert (await client.get(f"/sessions/{created['id']}/stability")).status_code == 409

    recorded = await recorded_session(client, db, participant, tremor_deg=0.6)
    unpublished = await client.post(f"/sessions/{recorded}/publish")
    assert unpublished.status_code == 409
    assert unpublished.json()["code"] == "conflict"


async def test_session_with_many_lost_samples_is_rejected(client, db, participant):
    session_id = await recorded_session(client, db, participant, lost=300, tremor_deg=0.6)
    recorded = (await client.get(f"/sessions/{session_id}")).json()
    assert recorded["valid_pct"] == pytest.approx(80.0)

    body = (await client.post(f"/sessions/{session_id}/check")).json()
    assert body["status"] == "rejected"
    assert "валидных отсчётов" in body["reject_reason"]
    assert body["destabilized"] is None

    verdict = (await client.get(f"/sessions/{session_id}/stability")).json()["verdict"]
    assert verdict.startswith("брак")
    # брак в датасет не попадает
    assert (await client.post(f"/sessions/{session_id}/publish")).status_code == 409


async def test_static_session_is_rejected_as_tracking_failure(client, db, participant):
    body = await checked_session(client, db, participant, static=True)
    assert body["status"] == "rejected"
    assert "неподвижен" in body["reject_reason"]


async def test_delete_session_cascades_to_samples_and_views(client, db, participant, exhibit):
    session_id = await recorded_session(client, db, participant, tremor_deg=0.6)
    view = {"exhibit_id": exhibit["id"], "dwell_ms": 1500}
    await client.post(f"/sessions/{session_id}/views", json=view)

    assert (await client.delete(f"/sessions/{session_id}")).status_code == 204
    samples = await db.scalar(select(func.count()).select_from(GazeSample))
    views = await db.scalar(select(func.count()).select_from(ExhibitView))
    assert (samples, views) == (0, 0)
    assert (await client.delete(f"/sessions/{session_id}")).status_code == 404


# ---------------------------------------------------------------- сессии: список


async def test_session_list_filters_sort_and_pagination(client, db, participant, group):
    for amplitude in (0.2, 0.5, 0.8):  # тремор около 0,14 / 0,35 / 0,57 градуса
        await checked_session(client, db, participant, tremor_deg=amplitude)
    await recorded_session(client, db, participant, n=1400, tremor_deg=0.3)  # не проверена
    await client.post("/sessions", json={"participant_id": participant["id"]})  # created

    everything = (await client.get("/sessions", params={"limit": 100})).json()
    assert len(everything) == 5

    checked = (await client.get("/sessions", params={"status": "checked"})).json()
    assert len(checked) == 3
    yes = (await client.get("/sessions", params={"destabilized": "true"})).json()
    no = (await client.get("/sessions", params={"destabilized": "false"})).json()
    assert (len(yes), len(no)) == (2, 1)

    by_group = (await client.get("/sessions", params={"group_id": group["id"]})).json()
    assert len(by_group) == 5
    assert (await client.get("/sessions", params={"group_id": 999})).json() == []
    assert (await client.get("/sessions", params={"participant_id": 999})).json() == []

    params = {"status": "checked", "sort": "-tremor_rms_deg"}
    desc = (await client.get("/sessions", params=params)).json()
    tremors = [s["tremor_rms_deg"] for s in desc]
    assert tremors == sorted(tremors, reverse=True)

    middle = await client.get(
        "/sessions",
        params={"status": "checked", "sort": "tremor_rms_deg", "limit": 1, "offset": 1},
    )
    assert [s["tremor_rms_deg"] for s in middle.json()] == [sorted(tremors)[1]]

    # сессии без тремора (NULL) при сортировке идут в конце
    nulls_last = (await client.get("/sessions", params={"sort": "-tremor_rms_deg"})).json()
    assert nulls_last[0]["tremor_rms_deg"] is not None
    assert nulls_last[-1]["tremor_rms_deg"] is None

    assert (await client.get("/sessions", params={"sort": "bogus"})).status_code == 422
    assert (await client.get("/sessions", params={"status": "bogus"})).status_code == 422
    assert (await client.get("/sessions", params={"limit": 101})).status_code == 422


# ---------------------------------------------------------------- dwell-click


async def test_dwell_click_rule(client, db, participant, exhibit):
    session_id = await recorded_session(client, db, participant, tremor_deg=0.6)
    url = f"/sessions/{session_id}/views"

    too_short = await client.post(url, json={"exhibit_id": exhibit["id"], "dwell_ms": 999})
    assert too_short.status_code == 422
    assert too_short.json()["code"] == "rule_violation"

    first = await client.post(url, json={"exhibit_id": exhibit["id"], "dwell_ms": 1000})
    assert first.status_code == 201
    assert (first.json()["dwell_ms"], first.json()["views_count"]) == (1000, 1)

    # повторный просмотр суммируется в той же записи
    again = await client.post(url, json={"exhibit_id": exhibit["id"], "dwell_ms": 1500})
    assert again.status_code == 201
    assert (again.json()["dwell_ms"], again.json()["views_count"]) == (2500, 2)
    assert len((await client.get(url)).json()) == 1


async def test_view_errors(client, db, participant, exhibit):
    session_id = await recorded_session(client, db, participant, tremor_deg=0.6)
    url = f"/sessions/{session_id}/views"

    assert (await client.post(url, json={"exhibit_id": 999, "dwell_ms": 2000})).status_code == 404
    valid = {"exhibit_id": exhibit["id"], "dwell_ms": 2000}
    assert (await client.post("/sessions/999/views", json=valid)).status_code == 404
    assert (await client.get("/sessions/999/views")).status_code == 404

    zero = await client.post(url, json={"exhibit_id": exhibit["id"], "dwell_ms": 0})
    assert zero.status_code == 422
    assert zero.json()["code"] == "validation_error"

    created = (await client.post("/sessions", json={"participant_id": participant["id"]})).json()
    not_recorded = await client.post(f"/sessions/{created['id']}/views", json=valid)
    assert not_recorded.status_code == 409

    rejected = await checked_session(client, db, participant, n=1300, static=True)
    assert rejected["status"] == "rejected"
    on_rejected = await client.post(f"/sessions/{rejected['id']}/views", json=valid)
    assert on_rejected.status_code == 409


# ---------------------------------------------------------------- аналитика


async def test_analytics(client, db, group):
    control = await create_group(client, "Контрольная", is_control=True)
    await create_group(client, "Пустая группа")
    p_main = await create_participant(client, group, "P-001")
    p_control = await create_participant(client, control, "C-001")
    e1 = await create_exhibit(client, "Экспонат 1")
    e2 = await create_exhibit(client, "Экспонат 2")

    s_yes = await recorded_session(client, db, p_main, tremor_deg=0.6)
    s_no = await recorded_session(client, db, p_main, n=1400, tremor_deg=0.05)
    s_ctrl = await recorded_session(client, db, p_control, n=1450, tremor_deg=0.05)
    s_bad = await recorded_session(client, db, p_main, n=1300, static=True)

    async def view(session_id, exhibit_id, dwell_ms):
        resp = await client.post(
            f"/sessions/{session_id}/views", json={"exhibit_id": exhibit_id, "dwell_ms": dwell_ms}
        )
        assert resp.status_code == 201

    await view(s_yes, e1["id"], 2000)
    await view(s_yes, e2["id"], 1000)
    await view(s_no, e1["id"], 1500)
    await view(s_ctrl, e2["id"], 3000)
    await view(s_bad, e1["id"], 5000)  # сессия окажется браком и не попадёт в аналитику

    for session_id in (s_yes, s_no, s_ctrl, s_bad):
        assert (await client.post(f"/sessions/{session_id}/check")).status_code == 200
    await client.post(f"/sessions/{s_yes}/publish")  # in_dataset тоже учитывается

    top = (await client.get("/analytics/dwell-by-exhibit")).json()
    assert [row["title"] for row in top] == ["Экспонат 2", "Экспонат 1"]
    assert top[0]["total_dwell_ms"] == 4000
    assert top[0]["sessions_count"] == 2
    assert top[0]["avg_dwell_ms"] == pytest.approx(2000.0)
    assert top[1]["total_dwell_ms"] == 3500  # 5000 мс из брака не учтены
    assert len((await client.get("/analytics/dwell-by-exhibit", params={"top": 1})).json()) == 1
    assert (await client.get("/analytics/dwell-by-exhibit", params={"top": 0})).status_code == 422

    report = (await client.get("/analytics/stability-by-group")).json()
    groups = {row["group_name"]: row for row in report}
    main = groups["Нарушения моторики"]
    counts = (main["sessions_analyzed"], main["destabilized_yes"], main["destabilized_no"])
    assert counts == (2, 1, 1)
    assert main["rejected"] == 1
    assert main["share_yes"] == pytest.approx(0.5)
    assert main["is_control"] is False
    ctrl = groups["Контрольная"]
    assert (ctrl["sessions_analyzed"], ctrl["destabilized_yes"], ctrl["share_yes"]) == (1, 0, 0.0)
    assert ctrl["is_control"] is True
    empty = groups["Пустая группа"]
    assert empty["sessions_analyzed"] == 0
    assert empty["share_yes"] is None
    assert empty["mean_tremor_rms_deg"] is None


# ---------------------------------------------------------------- формат ошибок и интерфейс


async def test_unified_error_format(client):
    not_found = await client.get("/sessions/999")
    assert not_found.status_code == 404
    assert not_found.json() == {"detail": "Сессия не найдена", "code": "not_found"}

    invalid = await client.post("/groups", json={})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"
    assert isinstance(invalid.json()["detail"], list)

    # старые эндпоинты (HTTPException) тоже отвечают в едином формате
    old = await client.get("/users/999")
    assert old.status_code == 404
    assert old.json()["code"] == "http_404"


async def test_web_interface_is_served(client):
    page = await client.get("/ui/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "VR-музей" in page.text

    root = await client.get("/")
    assert root.status_code == 307
    assert root.headers["location"] == "/ui/"
