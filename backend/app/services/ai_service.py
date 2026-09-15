"""Абстрактный слой AI-провайдеров с поддержкой OpenRouter, OpenAI и Google Gemini."""
import json
import re
import httpx
from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator
from app.config import settings
from app.security import encrypt_api_key, decrypt_api_key
from app.database import AuthSessionLocal
from app.models.auth_models import AppSetting
from sqlalchemy import select


async def get_ai_settings() -> dict:
    """Загрузить настройки AI из БД."""
    async with AuthSessionLocal() as session:
        result = await session.execute(select(AppSetting))
        rows = {r.key: r.value for r in result.scalars().all()}

    return {
        "provider": rows.get("ai_provider", settings.AI_PROVIDER),
        "api_key": decrypt_api_key(rows.get("ai_api_key", "")) or settings.AI_API_KEY,
        "model": rows.get("ai_model", settings.AI_MODEL),
        "base_url": rows.get("ai_base_url", "") or settings.AI_BASE_URL,
    }


def _clean_json(text: str) -> dict:
    """Очищает ответ AI от markdown-блоков и парсит JSON."""
    text = text.strip()
    # Удаляем ```json ... ``` обёртку
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    # Иногда AI добавляет описание до/после JSON
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace + 1]
    return json.loads(text)


# Максимальный размер куска текста, отправляемого в AI за один запрос.
# Большие расписания режутся НЕ по середине, а по логическим границам
# (перед началом блока преподавателя), чтобы ни одна пара не потерялась.
# Небольшой размер + запас по времени: бесплатные модели медленные.
CHUNK_SIZE = 6000

# Таймаут одного запроса к AI. Бесплатные модели могут думать несколько минут.
AI_TIMEOUT = 300.0

# Сколько раз повторять запрос по куску при сетевом сбое/таймауте.
AI_RETRIES = 3


def split_schedule_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Режет текст расписания на куски, не разрывая записи посередине.

    Старается разрезать перед строкой, похожей на начало блока
    (ФИО преподавателя / название дня / номер дня недели).
    """
    if len(text) <= chunk_size:
        return [text]

    # Границы, по которым безопасно резать: перед ФИО или днём недели
    boundary = re.compile(
        r"(?=^\s*(?:[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.|[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+"
        r"|Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье"
        r"|\d{1,2}\.\d{1,2}\.\d{2,4}))",
        re.MULTILINE,
    )
    points = [m.start() for m in boundary.finditer(text)]
    points = [p for p in points if p > 0] + [len(text)]

    chunks: list[str] = []
    start = 0
    for p in points:
        if p - start >= chunk_size:
            # Если ближайшая граница слишком далеко — режем жёстко
            if p - start > chunk_size * 2:
                while start + chunk_size < p:
                    chunks.append(text[start:start + chunk_size])
                    start += chunk_size
                continue
            chunks.append(text[start:p])
            start = p

    if start < len(text):
        remainder = text[start:]
        # Остаток может быть слишком большим — дорезаем
        while len(remainder) > chunk_size * 2:
            chunks.append(remainder[:chunk_size])
            remainder = remainder[chunk_size:]
        if remainder.strip():
            chunks.append(remainder)

    return [c for c in chunks if c.strip()]


def _chunk_boundaries(text: str, chunk_size: int) -> list[tuple[int, int]]:
    """Границы кусков в виде пар (начало, конец) — без склейки строк."""
    chunks = split_schedule_text(text, chunk_size)
    bounds: list[tuple[int, int]] = []
    pos = 0
    for c in chunks:
        start = text.find(c, pos)
        if start < 0:
            start = pos
        bounds.append((start, start + len(c)))
        pos = start + len(c)
    return bounds


async def _request_with_retry(coro_factory, chunk: str, label: str = "") -> list[dict]:
    """Выполняет запрос к AI с повторами при таймауте/сетевом сбое.

    coro_factory(chunk) -> list[dict]. При сбое дробит кусок пополам
    и пробует части отдельно, чтобы не терять данные целиком.
    """
    import asyncio as _asyncio

    last_err: Exception | None = None
    for attempt in range(AI_RETRIES):
        try:
            return await coro_factory(chunk)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            # Ошибки лимита/ключа повторять бессмысленно
            if "429" in msg or "rate limit" in msg or "401" in msg or "invalid_api_key" in msg:
                raise
            if attempt < AI_RETRIES - 1:
                await _asyncio.sleep(2 * (attempt + 1))

    # Все попытки исчерпаны — пробуем разбить кусок пополам
    if len(chunk) > 1500:
        mid = len(chunk) // 2
        # Ищем перенос строки рядом с серединой
        nl = chunk.find("\n", mid)
        if nl == -1 or nl > mid + 500:
            nl = chunk.rfind("\n", 0, mid)
        if nl > 0:
            left, right = chunk[:nl], chunk[nl:]
            out: list[dict] = []
            for part in (left, right):
                try:
                    out.extend(await coro_factory(part))
                except Exception:
                    pass
            if out:
                return out

    raise last_err if last_err else RuntimeError("AI request failed")


async def _parse_chunks_parallel(coro_factory, chunks: list[str], limit: int = 3) -> list[list[dict]]:
    """Разбирает куски параллельно (не более `limit` одновременно).

    Параллельность критична: 4 куска последовательно не укладываются
    в таймаут HTTP-запроса к нашему API. Один упавший кусок не роняет
    остальные — его результат просто пустой.
    """
    import asyncio as _asyncio

    sem = _asyncio.Semaphore(limit)
    results: list[list[dict]] = [[] for _ in chunks]

    async def run(idx: int, chunk: str) -> None:
        async with sem:
            try:
                results[idx] = await _request_with_retry(coro_factory, chunk)
            except Exception:
                results[idx] = []

    await _asyncio.gather(*(run(i, c) for i, c in enumerate(chunks)))
    return results


class AIProvider(ABC):
    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Генератор чанков стриминга."""

    @abstractmethod
    async def parse_schedule(self, text: str, teacher_filter: str = "", user_query: str = "") -> dict:
        """Парсинг расписания с фильтрацией по преподавателю."""

    @abstractmethod
    async def parse_schedule_all(self, text: str, user_query: str = "") -> dict:
        """Парсинг ВСЕХ записей расписания с определением преподавателя для каждой."""
        ...


class OpenAICompatibleProvider(AIProvider):
    """Для OpenRouter и любых OpenAI-совместимых API."""

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(AI_TIMEOUT, connect=30.0))

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "http://localhost:3000"
            headers["X-Title"] = "Teacher AI Assistant"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        async with self.client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise Exception(f"AI API error ({response.status_code}): {error_text.decode()[:500]}")

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        # Провайдер может прислать чанк с пустым choices
                        # (usage/keep-alive/служебные события) — не падаем.
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def parse_schedule(self, text: str, teacher_filter: str = "", user_query: str = "") -> dict:
        """Парсинг через AI с фильтрацией по преподавателю."""
        filter_instruction = ""
        if teacher_filter:
            filter_instruction = f"""
ВАЖНО: Извлекай ТОЛЬКО занятия, которые ведёт преподаватель **{teacher_filter}**.
Игнорируй занятия других преподавателей.
Если пользователь написал запрос, интерпретируй его: 
- "мои пары" = только занятия {teacher_filter}
- название группы = только для этой группы
- конкретный день = только этот день
"""
        if user_query:
            filter_instruction += f'\nЗапрос пользователя: "{user_query}"'

        system_prompt = f"""Ты — парсер расписания. Извлеки из текста структурированное расписание занятий.
Для каждой записи определи:
- title: название предмета или события
- day_of_week: день недели (0=ПН, 1=ВТ, 2=СР, 3=ЧТ, 4=ПТ, 5=СБ, 6=ВС)
- start_time: время начала (HH:MM)
- end_time: время окончания (HH:MM)
- group_name: группа или класс
- room: аудитория
- type: тип ("lesson", "meeting", "other")
{filter_instruction}

Верни ТОЛЬКО JSON без markdown-форматирования в формате:
{{"items": [{{"title": "...", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "...", "room": "...", "type": "lesson", "source": "pdf_import"}}]}}

Правила:
- Если день недели указан словами (понедельник, вторник...) — переведи в число 0-6
- Для дат: определи день недели по дате (21.09.26 — понедельник, 22.09.26 — вторник, и т.д.)
- Если время окончания не указано — добавь 1 час 30 минут к началу
- Если группа/аудитория не указаны — оставь пустыми
- source всегда "pdf_import"
- НЕ включай markdown-разметку, верни ЧИСТЫЙ JSON
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Расписание для парсинга:\n\n{text}"},
        ]

        # Используем не-стриминговый вызов через httpx напрямую
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.base_url and "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "http://localhost:5173"
            headers["X-Title"] = "Teacher AI Assistant"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "stream": False,
        }

        async def _parse_chunk(chunk: str) -> list[dict]:
            resp = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Расписание для парсинга:\n\n{chunk}"},
                    ],
                    "temperature": 0.1,
                    "stream": False,
                },
            )
            if resp.status_code != 200:
                raise Exception(f"AI API error ({resp.status_code}): {resp.text[:500]}")
            return _clean_json(resp.json()["choices"][0]["message"]["content"]).get("items", [])

        # Большие расписания разбираем частями — иначе AI теряет хвост файла.
        # Чанки идут ПАРАЛЛЕЛЬНО: последовательная обработка упирается в таймаут.
        chunks = split_schedule_text(text)
        all_items: list[dict] = []
        seen: set[tuple] = set()

        results = await _parse_chunks_parallel(_parse_chunk, chunks)
        for chunk_items in results:
            for item in chunk_items:
                key = (
                    item.get("day_of_week"),
                    str(item.get("start_time", "")),
                    str(item.get("end_time", "")),
                    str(item.get("title", "")).lower().strip(),
                    str(item.get("group_name", "")).lower().strip(),
                )
                if key in seen:
                    continue
                seen.add(key)
                all_items.append(item)

        return {"items": all_items}

    async def parse_schedule_all(self, text: str, user_query: str = "") -> dict:
        """Парсинг ВСЕХ записей с определением преподавателя для каждой."""
        extra = ""
        if user_query:
            extra = f'\nЗапрос пользователя: "{user_query}"'

        system_prompt = f"""Ты — парсер расписания. Извлеки ВСЕ занятия из текста.
Для КАЖДОЙ записи определи:
- title: название предмета
- day_of_week: день недели (0=ПН, 1=ВТ, 2=СР, 3=ЧТ, 4=ПТ, 5=СБ, 6=ВС)
- start_time: время начала (HH:MM)
- end_time: время окончания (HH:MM)
- group_name: группа
- room: аудитория
- type: тип ("lesson", "meeting", "other")
- teacher: ФИО преподавателя (извлеки из текста, например "Гаврилов А.И.", "ст.пр. Певцова Л.С." → "Певцова Л.С.")
{extra}

Верни ТОЛЬКО JSON:
{{"items": [{{"title": "...", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "...", "room": "...", "type": "lesson", "teacher": "Фамилия И.О.", "source": "pdf_import"}}]}}

Правила:
- Дни: 0=ПН…6=ВС. Даты: 21.09.26 — понедельник, 22.09.26 — вторник и т.д.
- teacher ОБЯЗАТЕЛЕН — извлеки ФИО из ячейки (убери "доц.", "ст.пр.", "асс.")
- Если время окончания не указано — начало + 1ч30м
- НЕ включай markdown, верни ЧИСТЫЙ JSON"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Расписание:\n\n{text}"},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.base_url and "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "http://localhost:5173"
            headers["X-Title"] = "Teacher AI Assistant"

        async def _parse_chunk(chunk: str) -> list[dict]:
            resp = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Расписание:\n\n{chunk}"},
                    ],
                    "temperature": 0.1,
                    "stream": False,
                },
            )
            if resp.status_code != 200:
                raise Exception(f"AI API error ({resp.status_code}): {resp.text[:500]}")
            parsed = _clean_json(resp.json()["choices"][0]["message"]["content"])
            return parsed.get("items", [])

        # Большое расписание отправляем частями, чтобы не потерять преподавателей.
        # Куски идут ПАРАЛЛЕЛЬНО — так парсинг укладывается в таймаут.
        chunks = split_schedule_text(text)
        all_items: list[dict] = []
        seen: set[tuple] = set()

        results = await _parse_chunks_parallel(_parse_chunk, chunks)
        for chunk_items in results:
            for item in chunk_items:
                key = (
                    str(item.get("teacher", "")).lower().strip(),
                    item.get("day_of_week"),
                    str(item.get("start_time", "")),
                    str(item.get("end_time", "")),
                    str(item.get("title", "")).lower().strip(),
                    str(item.get("group_name", "")).lower().strip(),
                )
                if key in seen:
                    continue
                seen.add(key)
                all_items.append(item)

        return {"items": all_items}


class GeminiProvider(AIProvider):
    """Google Gemini API."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(AI_TIMEOUT, connect=30.0))

    async def _call_gemini(self, messages: list[dict], stream: bool = False, **kwargs):
        # Конвертируем OpenAI-формат в Gemini
        system_parts = []
        contents = []

        for msg in messages:
            if msg["role"] == "system":
                system_parts.append({"text": msg["content"]})
            elif msg["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif msg["role"] == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

        system_instruction = None
        if system_parts:
            system_instruction = {"parts": system_parts}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:{'streamGenerateContent' if stream else 'generateContent'}"
        params = {"key": self.api_key}

        body = {
            "contents": contents[-1:] if len(contents) == 1 else contents,  # Gemini ожидает историю
        }
        # Правильный формат для Gemini: все сообщения в одном объекте contents
        if len(contents) > 1:
            body["contents"] = contents
        else:
            body["contents"] = [contents[0]] if contents else [{"role": "user", "parts": [{"text": ""}]}]

        if system_instruction:
            body["systemInstruction"] = system_instruction

        if "temperature" in kwargs:
            body["generationConfig"] = {"temperature": kwargs["temperature"]}

        return url, params, body

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        url, params, body = await self._call_gemini(messages, stream=True, **kwargs)

        async with self.client.stream("POST", url, params=params, json=body) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise Exception(f"Gemini API error ({response.status_code}): {error_text.decode()[:500]}")

            buffer = ""
            async for chunk in response.aiter_bytes():
                buffer += chunk.decode()
                # Парсим чанки Gemini
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith("["):
                        continue
                    try:
                        data = json.loads(line)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                if "text" in part:
                                    yield part["text"]
                    except json.JSONDecodeError:
                        continue

    async def parse_schedule(self, text: str, teacher_filter: str = "", user_query: str = "") -> dict:
        """Парсинг через Gemini с фильтрацией по преподавателю."""
        filter_instruction = ""
        if teacher_filter:
            filter_instruction = f"""
ВАЖНО: Извлекай ТОЛЬКО занятия преподавателя **{teacher_filter}**.
Игнорируй занятия других преподавателей.
"""
        if user_query:
            filter_instruction += f'\nЗапрос пользователя: "{user_query}"'

        system_prompt = f"""Ты — парсер расписания. Извлеки из текста структурированное расписание занятий.
{filter_instruction}
Верни ТОЛЬКО JSON без markdown в формате:
{{"items": [{{"title": "...", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "...", "room": "...", "type": "lesson", "source": "pdf_import"}}]}}
Дни: 0=ПН, 1=ВТ, 2=СР, 3=ЧТ, 4=ПТ, 5=СБ, 6=ВС."""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": f"Расписание:\n\n{text}"}]}],
            "generationConfig": {"temperature": 0.1},
        }

        response = await self.client.post(url, params=params, json=body)
        if response.status_code != 200:
            raise Exception(f"Gemini API error ({response.status_code}): {response.text[:500]}")

        data = response.json()
        result_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _clean_json(result_text)

    async def parse_schedule_all(self, text: str, user_query: str = "") -> dict:
        """Парсинг ВСЕХ записей с определением преподавателя (Gemini)."""
        extra = f'\nЗапрос пользователя: "{user_query}"' if user_query else ""

        system_prompt = f"""Ты — парсер расписания. Извлеки ВСЕ занятия.
Для КАЖДОЙ: title, day_of_week (0=ПН…6=ВС), start_time, end_time, group_name, room, type, teacher.
teacher — ФИО из ячейки без званий (доц., ст.пр., асс.).
{extra}

Верни ТОЛЬКО JSON:
{{"items": [{{"title": "...", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "...", "room": "...", "type": "lesson", "teacher": "Фамилия И.О.", "source": "pdf_import"}}]}}
Даты: 21.09.26=ПН, 22.09.26=ВТ…"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": f"Расписание:\n\n{text}"}]}],
            "generationConfig": {"temperature": 0.1},
        }
        response = await self.client.post(url, params=params, json=body)
        if response.status_code != 200:
            raise Exception(f"Gemini API error ({response.status_code}): {response.text[:500]}")

        data = response.json()
        result_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _clean_json(result_text)


async def create_ai_provider() -> AIProvider:
    """Фабрика: создаёт нужный AI-провайдер на основе настроек из БД."""
    ai_config = await get_ai_settings()
    provider = ai_config["provider"]
    api_key = ai_config["api_key"]
    model = ai_config["model"]
    base_url = ai_config["base_url"]

    if not api_key:
        raise Exception("API-ключ AI не настроен. Добавьте ключ в админ-панели.")

    if provider == "gemini":
        return GeminiProvider(api_key=api_key, model=model)
    else:
        # openrouter, openai, и любые OpenAI-совместимые
        if provider == "openai":
            base_url = base_url or "https://api.openai.com/v1"
        elif provider == "openrouter":
            base_url = base_url or "https://openrouter.ai/api/v1"
        return OpenAICompatibleProvider(api_key=api_key, model=model, base_url=base_url)


async def build_system_context(user_id: str) -> str:
    """Системный промпт: честная картина календаря по ДАТАМ + задачи + активный импорт.

    Расписание показывается развёрткой на ближайшие 14 дней (недельные шаблоны
    с weeks-паритетом и датированные занятия слиты в календарь по датам), чтобы
    отвечать «какие пары завтра / когда ближайший выходной» правдой, а не по
    дням недели вслепую.
    """
    from app.database import DataSessionLocal
    from sqlalchemy import select
    from app.models.data_models import Schedule, Task, ScheduleImport, ImportState
    from app.services.import_expander import monday_of, week_number, weeks_match
    from datetime import date, timedelta
    import json as _json

    today = date.today()
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    short = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

    async with DataSessionLocal() as session:
        r = await session.execute(
            select(Schedule).where(Schedule.user_id == user_id)
            .order_by(Schedule.day_of_week, Schedule.start_time))
        schedules = r.scalars().all()

        r = await session.execute(
            select(Task).where(Task.user_id == user_id).where(Task.status != "done")
            .order_by(Task.due_date))
        tasks = r.scalars().all()

        imp = (await session.execute(
            select(ScheduleImport)
            .where(ScheduleImport.user_id == user_id)
            .where(ScheduleImport.state.in_([ImportState.ASK_PERIOD, ImportState.ASK_END, ImportState.READY]))
            .order_by(ScheduleImport.created_at.desc())
        )).scalars().first()

    templates = [s for s in schedules if s.event_date is None]
    dated = [s for s in schedules if s.event_date is not None]
    first_mon = monday_of(today)

    ctx = "Ты — ИИ-помощник преподавателя. Отвечай на русском языке.\n\n"
    ctx += f"## Сегодня: {today.isoformat()} ({days[today.weekday()]})\n\n"

    # ── Календарь по датам на 14 дней ──
    ctx += "## Календарь на ближайшие 14 дней (фактические даты):\n"
    any_day = False
    for k in range(14):
        d = today + timedelta(days=k)
        n = week_number(d, first_mon)
        items = []
        for s in dated:
            if s.event_date == d:
                items.append(f"{s.start_time:%H:%M}-{s.end_time:%H:%M} {s.title}"
                             + (f" | гр. {s.group_name}" if s.group_name else "")
                             + (f" | ауд {s.room}" if s.room else "") + " (конкретная дата)")
        for s in templates:
            if s.day_of_week != d.weekday():
                continue
            if s.weeks and not weeks_match(s.weeks, n):
                continue
            tag = "каждую неделю" if not s.weeks else f"недели: {s.weeks}"
            items.append(f"{s.start_time:%H:%M}-{s.end_time:%H:%M} {s.title}"
                         + (f" | гр. {s.group_name}" if s.group_name else "")
                         + (f" | ауд {s.room}" if s.room else "") + f" (шаблон, {tag})")
        label = "СЕГОДНЯ" if k == 0 else ("ЗАВТРА" if k == 1 else "")
        head = f"### {d.isoformat()} ({days[d.weekday()]}{', неделя ' + str(n) if n else ''})" + (f" ← {label}" if label else "")
        if items:
            any_day = True
            ctx += head + "\n" + "\n".join(f"- {i}" for i in sorted(items)) + "\n"
        elif label:
            ctx += head + "\n- занятий нет\n"
    if not any_day and not dated and not templates:
        ctx += "- расписание пустое\n"

    # ── Дальше по датам (кроме окна 14 дней) ──
    far = sorted({s.event_date for s in dated if s.event_date > today + timedelta(days=13)})
    if far:
        ctx += "\n## Датированные занятия позже 14 дней (по датам):\n"
        for d in far[:40]:
            cnt = sum(1 for s in dated if s.event_date == d)
            ctx += f"- {d.isoformat()} ({short[d.weekday()]}): {cnt} зан.\n"

    if imp is not None:
        try:
            items_cnt = len(_json.loads(imp.items_json or "[]"))
        except Exception:
            items_cnt = 0
        state_txt = {
            "ASK_PERIOD": "система ждёт ответ пользователя «на ближайшую неделю или на семестр?» — "
                          "если пользователь ответит тебе, переспроси то же самое или напомни варианты",
            "ASK_END": "выбран семестр, система ждёт дату окончания («до 30 декабря»)",
            "READY": "развёрнуто по датам и ждёт карточки подтверждения",
        }.get(imp.state.name if hasattr(imp.state, "name") else str(imp.state), "")
        ctx += (f"\n## Активный импорт файла «{imp.filename}»: {items_cnt} распознанных занятий "
                f"(по преподавателям — см. вопрос системы). Статус: {state_txt}.\n"
                "Содержимое файла построчно ты НЕ видишь; массовые операции по импорту "
                "система делает сама через карточки — create_schedule по памяти НЕ создавай.\n")

    if tasks:
        ctx += "\n## Активные задачи (заметки):\n"
        for t in tasks:
            scope = getattr(t, "scope", None)
            scope_val = scope.value if scope else "none"
            if t.due_date:
                due = f" (на {t.due_date.isoformat()}, {days[t.due_date.weekday()]})"
                overdue = " ПРОСРОЧЕНО!" if t.due_date < today else ""
            elif getattr(t, "due_month", None):
                due = f" (на месяц {t.due_month})"
                overdue = " ПРОСРОЧЕНО!" if t.due_month < today.strftime("%Y-%m") else ""
            elif getattr(t, "due_year", None):
                due = f" (на {t.due_year} год)"
                overdue = " ПРОСРОЧЕНО!" if t.due_year < today.year else ""
            else:
                due, overdue = " (без срока)", ""
            ctx += f"- [{scope_val}] {t.status.value}: {t.title}{due}{overdue}\n"
    else:
        ctx += "\n## Активные задачи: отсутствуют\n"

    ctx += ("\nОтвечай строго по календарю выше: «какие пары завтра» — бери блок с меткой "
            "ЗАВТРА; «когда ближайший выходной» — первый день без занятий, считая с сегодня. "
            "Если данных нет — так и скажи, не выдумывай.")
    ctx += "\nЕсли спрашивают «какие сегодня пары» — смотри записи помеченные «СЕГОДНЯ»."

    from app.services.chat_actions import TOOL_PROMPT
    ctx += TOOL_PROMPT

    return ctx
