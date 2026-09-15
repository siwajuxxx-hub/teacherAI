"""Проверка сообщений об ошибках входа через Vite-прокси (как в браузере)."""
import httpx

URL = "http://localhost:5173/api/auth/login"

cases = [
    ({"username": "nouser123", "password": "wrong"}, "нет пользователя"),
    ({"username": "admin", "password": "oops"}, "неверный пароль"),
    ({"username": "admin", "password": "admin"}, "верные данные"),
    ({"username": "x" * 200, "password": "y" * 200}, "очень длинные"),
    ({"username": "admin", "password": ""}, "пустой пароль"),
    ({"username": "", "password": ""}, "пустые поля"),
]

print("--- Через Vite-прокси :5173 (как в браузере) ---")
for creds, label in cases:
    try:
        r = httpx.post(URL, json=creds, timeout=20)
        body = r.content.decode("utf-8")[:100]
        print(f"{label:22} -> {r.status_code} {body}")
    except Exception as e:
        print(f"{label:22} -> ОШИБКА СОЕДИНЕНИЯ: {e}")

print("\n--- Напрямую в бэкенд :8000 ---")
for creds, label in cases:
    try:
        r = httpx.post("http://localhost:8000/api/auth/login", json=creds, timeout=20)
        body = r.content.decode("utf-8")[:100]
        print(f"{label:22} -> {r.status_code} {body}")
    except Exception as e:
        print(f"{label:22} -> ОШИБКА: {e}")