"""Смоук-тест запущенного сервиса: все эндпоинты и коды ответов из задания.

Запуск: python scripts/smoke_test.py [BASE_URL]   (по умолчанию http://127.0.0.1:8000)
Нужен только стандартный Python, сторонние пакеты не используются.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def parse(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, parse(raw), resp.headers
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, parse(raw), err.headers


checks = 0


def expect(method, path, code, body=None):
    global checks
    status, payload, headers = call(method, path, body)
    assert status == code, f"{method} {path}: ожидался {code}, получен {status}: {payload}"
    assert headers.get("X-Process-Time"), f"{method} {path}: нет заголовка X-Process-Time"
    checks += 1
    print(f"OK  {method:6} {path:40} -> {status}")
    return payload


email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"

user = expect("POST", "/users", 201, {"email": email, "name": "Смоук"})
expect("POST", "/users", 409, {"email": email, "name": "Дубль"})
expect("POST", "/users", 422, {"email": "not-an-email", "name": "X"})
assert expect("GET", f"/users/{user['id']}", 200)["email"] == email
expect("GET", "/users/999999", 404)

t1 = expect("POST", "/tasks", 201, {"title": "Первая", "owner_id": user["id"]})
assert t1["done"] is False and t1["description"] is None
t2 = expect("POST", "/tasks", 201, {"title": "Вторая", "done": True, "owner_id": user["id"]})
expect("POST", "/tasks", 404, {"title": "Без владельца", "owner_id": 999999})
expect("POST", "/tasks", 422, {"title": "", "owner_id": user["id"]})
expect("POST", "/tasks", 422, {"title": "x" * 201, "owner_id": user["id"]})

done = expect("GET", f"/tasks?done=true&owner_id={user['id']}", 200)
assert [t["id"] for t in done] == [t2["id"]], done
page = expect("GET", f"/tasks?owner_id={user['id']}&limit=1&offset=1", 200)
assert [t["id"] for t in page] == [t2["id"]], page
expect("GET", "/tasks?limit=0", 422)
expect("GET", "/tasks?limit=101", 422)

expect("GET", f"/tasks/{t1['id']}", 200)
expect("GET", "/tasks/999999", 404)

patched = expect("PATCH", f"/tasks/{t1['id']}", 200, {"done": True})
assert patched["done"] is True and patched["title"] == "Первая"  # остальные поля не тронуты
expect("PATCH", f"/tasks/{t1['id']}", 422, {"title": None})
expect("PATCH", "/tasks/999999", 404, {"done": True})

expect("DELETE", f"/tasks/{t2['id']}", 204)
expect("DELETE", f"/tasks/{t2['id']}", 404)
expect("GET", f"/tasks/{t2['id']}", 404)

print(f"\nВсе проверки пройдены: {checks}")
