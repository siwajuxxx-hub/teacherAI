"""Тест чата: SSE-стриминг и сохранение истории."""
import httpx
import json
import sys

BASE = "http://localhost:8000"

def main():
    # Логин
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("=== ТЕСТ 1: SSE стриминг ===")
    chunks = []
    assistant_id = None
    with httpx.stream("POST", f"{BASE}/api/chat/send", headers=headers,
                      json={"message": "Ответь одним словом: привет"}, timeout=90) as resp:
        print(f"HTTP статус: {resp.status_code}")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("chunk"):
                        chunks.append(data["chunk"])
                    if data.get("done"):
                        assistant_id = data.get("message_id")
                except json.JSONDecodeError:
                    pass

    full = "".join(chunks)
    print(f"Получено чанков: {len(chunks)}")
    print(f"Ответ AI: {full[:200]}")
    print(f"message_id: {assistant_id}")

    print()
    print("=== ТЕСТ 2: История содержит ОБА сообщения ===")
    h = httpx.get(f"{BASE}/api/chat/history", headers=headers, params={"limit": 6})
    history = h.json()
    for msg in history:
        content = msg["content"].replace("\n", " ")[:60]
        print(f"  [{msg['role']:9}] {content}")

    roles = [m["role"] for m in history]
    has_user = "user" in roles
    has_assistant = "assistant" in roles
    print()
    if has_user and has_assistant:
        print("✅ УСПЕХ: сохраняются и сообщения пользователя, и ответы AI")
    else:
        print(f"❌ ОШИБКА: user={has_user}, assistant={has_assistant}")
        sys.exit(1)

if __name__ == "__main__":
    main()