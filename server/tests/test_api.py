"""Тесты REST API «Менеджер задач». Обязательные тесты 1–9 из шага 4 задания + дополнительные."""

import pytest

# ---------- обязательные тесты (шаг 4) ----------


async def test_create_user_201(client):
    """1. Создание пользователя возвращает 201 и данные пользователя."""
    resp = await client.post("/users", json={"email": "marina@example.com", "name": "Марина"})
    assert resp.status_code == 200  # намеренная ошибка для проверки «красного» pipeline (шаг 8)
    body = resp.json()
    assert body["id"] == 1
    assert body["email"] == "marina@example.com"
    assert body["name"] == "Марина"
    assert "created_at" in body


async def test_duplicate_email_409(client):
    """2. Повторный email возвращает 409."""
    payload = {"email": "same@example.com", "name": "Первый"}
    assert (await client.post("/users", json=payload)).status_code == 201
    resp = await client.post("/users", json={**payload, "name": "Второй"})
    assert resp.status_code == 409
    assert "email" in resp.json()["detail"]


async def test_invalid_email_422(client):
    """3. Невалидный email возвращает 422 с указанием поля."""
    resp = await client.post("/users", json={"email": "not-an-email", "name": "X"})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["body", "email"]


async def test_create_task_201(client, user):
    """4. Создание задачи возвращает 201; done по умолчанию false, description необязателен."""
    resp = await client.post("/tasks", json={"title": "Сдать работу", "owner_id": user["id"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Сдать работу"
    assert body["done"] is False
    assert body["description"] is None
    assert body["owner_id"] == user["id"]


async def test_create_task_unknown_owner_404(client):
    """5. Задача с несуществующим владельцем — 404."""
    resp = await client.post("/tasks", json={"title": "Ничья", "owner_id": 999})
    assert resp.status_code == 404


async def test_filter_done_and_pagination(client, user):
    """6. Фильтр done и пагинация limit/offset."""
    for i in range(5):
        resp = await client.post(
            "/tasks", json={"title": f"Задача {i}", "done": i % 2 == 0, "owner_id": user["id"]}
        )
        assert resp.status_code == 201

    done = (await client.get("/tasks", params={"done": True})).json()
    assert [t["title"] for t in done] == ["Задача 0", "Задача 2", "Задача 4"]
    not_done = (await client.get("/tasks", params={"done": False})).json()
    assert [t["title"] for t in not_done] == ["Задача 1", "Задача 3"]

    page = await client.get("/tasks", params={"owner_id": user["id"], "limit": 2, "offset": 2})
    assert page.status_code == 200
    assert [t["title"] for t in page.json()] == ["Задача 2", "Задача 3"]


async def test_patch_changes_only_sent_fields(client, user):
    """7. PATCH меняет только переданные поля."""
    created = (
        await client.post(
            "/tasks",
            json={"title": "Исходная", "description": "Описание", "owner_id": user["id"]},
        )
    ).json()

    resp = await client.patch(f"/tasks/{created['id']}", json={"done": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["done"] is True
    assert body["title"] == "Исходная"
    assert body["description"] == "Описание"
    assert body["created_at"] == created["created_at"]


async def test_delete_then_get_404(client, user):
    """8. DELETE возвращает 204, после этого GET — 404."""
    task = (await client.post("/tasks", json={"title": "Удалить", "owner_id": user["id"]})).json()

    resp = await client.delete(f"/tasks/{task['id']}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert (await client.get(f"/tasks/{task['id']}")).status_code == 404


async def test_process_time_header(client):
    """9. Middleware добавляет заголовок X-Process-Time в каждый ответ."""
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert "x-process-time" in resp.headers
    assert float(resp.headers["x-process-time"]) >= 0


# ---------- дополнительные тесты ----------


async def test_get_user_200_and_404(client, user):
    assert (await client.get(f"/users/{user['id']}")).json()["email"] == user["email"]
    assert (await client.get("/users/999")).status_code == 404


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_out_of_range_422(client, limit):
    resp = await client.get("/tasks", params={"limit": limit})
    assert resp.status_code == 422


@pytest.mark.parametrize("title", ["", "x" * 201], ids=["empty", "201-chars"])
async def test_title_length_422(client, user, title):
    resp = await client.post("/tasks", json={"title": title, "owner_id": user["id"]})
    assert resp.status_code == 422


async def test_patch_explicit_null_title_422(client, user):
    task = (await client.post("/tasks", json={"title": "Есть", "owner_id": user["id"]})).json()
    resp = await client.patch(f"/tasks/{task['id']}", json={"title": None})
    assert resp.status_code == 422


async def test_patch_and_delete_unknown_task_404(client):
    assert (await client.patch("/tasks/999", json={"done": True})).status_code == 404
    assert (await client.delete("/tasks/999")).status_code == 404
