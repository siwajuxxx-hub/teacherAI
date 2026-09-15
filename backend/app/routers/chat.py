"""Чат: единый конвейер импорта + детерминированные намерения + AI-слой.

Архитектура (после редизайна):
  /upload   — файл → структурный парсер (xls/docx) или AI (pdf/txt) → ScheduleImport
              (машина состояний: ASK_PERIOD → ASK_END → READY) → карточка-вопрос
              или предложение IMPORT_PLAN.
  /send     — детерминированный детектор намерений (chat_intents): ответы на вопросы
              импорта, «добавь пары X ко мне», «перенеси в календарь X», «распредели
              всем», «очисти календарь ...». Всё остальное — AI; его действия
              заземляются на БД (chat_exec) и тоже становятся карточкой Proposal.
  /confirm  —执行 по proposal_id (+ опциональные индексы строк). Сырых действий
              клиент не присылает НИКОГДА.
  /history  — сообщения + висящие proposal/question (F5 ничего не теряет).
"""
import json
import re
import uuid
import asyncio
import logging
import os as _os
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_data_session, DataSessionLocal
from app.models.data_models import (
    ChatHistory, ImportKind, ImportState, Proposal, ProposalStatus, ScheduleImport,
)
from app.models.auth_models import User
from app.schemas.data_schemas import ChatMessageRequest, ChatMessageOut
from app.security import get_current_user, require_teacher_or_above
from app.services.ai_service import create_ai_provider, build_system_context
from app.services.file_parser import extract_text_from_file
from app.services.xls_schedule_parser import parse_xls_schedule, extract_xls_text
from app.services.docx_schedule_parser import parse_docx_schedule
from app.services.chat_actions import extract_actions
from app.services import chat_exec
from app.services.chat_intents import (
    Intent, detect_intent, parse_date_loose,
)
from app.services.import_expander import (
    expand_items, monday_of, next_week_window,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Чат"])

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MAX_FILE_BYTES = 10 * 1024 * 1024

# create_schedule из текста легитимен, только когда пользователь сам назвал
# день/дату/время. «Добавь расписание Федуловой» конкретики не содержит —
# это сценарий импорта, там данные строго из файла.
_WHEN_RE = re.compile(
    r"\d{1,2}[:.\s]\d{2}"
    r"|понед|вторник|сред[а-яё]|четверг|пятниц|суббот|воскрес"
    r"|\b(пн|вт|ср|чт|пт|сб|вс)\b"
    r"|завтра|сегодня|послезавтра"
    r"|\d{1,2}\s*(янв|фев|мар|апр|ма[йт]|июн|июл|авг|сент|окт|нояб|декабр)"
    r"|\d{4}-\d{2}-\d{2}",
    re.IGNORECASE,
)

_IMPORT_FILE_NOTE = (
    "\n\n⚠️ Похоже, речь о парах из файла — содержимое файлов я не вижу и выдумывать "
    "занятия не буду. Если импорт ещё активен — система сама спросит период и покажет "
    "карточку. Если файл был давно — прикрепите его заново (📎) вместе с запросом."
)


class ConfirmBody(BaseModel):
    proposal_id: str
    selected: list[int] | None = None


class RejectBody(BaseModel):
    proposal_id: str


# ─── Утилиты ──────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def _store_msg(db: AsyncSession, user_id: str, role: str, content: str,
                     ctx_type: str | None = None) -> str:
    m = ChatHistory(user_id=user_id, role=role, content=content,
                    context_type=ctx_type, context_id=str(uuid.uuid4()))
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m.id


async def _active_import(db: AsyncSession, user_id: str) -> ScheduleImport | None:
    """Последний незавершённый импорт (живёт неделю)."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    r = await db.execute(
        select(ScheduleImport)
        .where(ScheduleImport.user_id == user_id)
        .where(ScheduleImport.state.in_([ImportState.ASK_PERIOD, ImportState.ASK_END, ImportState.READY]))
        .where(ScheduleImport.created_at >= cutoff)
        .order_by(ScheduleImport.created_at.desc())
    )
    return r.scalars().first()


def _state_val(v) -> str:
    """Имя состояния ('READY', 'ASK_PERIOD') — совпадает с тем, что лежит в БД
    (SAEnum хранит имена членов) и с ожиданиями клиента."""
    return v.name if hasattr(v, "name") else str(v)


def _period_question(imp: ScheduleImport, today: date) -> dict:
    w_start, w_end = next_week_window(today)
    if _state_val(imp.state) == "ASK_PERIOD":
        return {
            "text": ("На какой период разложить недели из файла? Ответьте словом или "
                     "напишите дату, например «с 8 сентября до 30 декабря»."),
            "replies": [
                {"label": f"На ближайшую неделю ({w_start.strftime('%d.%m')}–{w_end.strftime('%d.%m')})",
                 "value": "на ближайшую неделю"},
                {"label": "На семестр", "value": "на семестр"},
                {"label": "Отмена", "value": "отмена"},
            ],
        }
    if _state_val(imp.state) == "ASK_END":
        return {
            "text": ("До какой даты раскладывать пары семестра? Например: «до 30 декабря» "
                     "или «30.12.2026». Неделя-1 сейчас считается с "
                     f"{(imp.period_start or monday_of(today)).strftime('%d.%m')}"
                     " (можно «начни неделю-1 с 8 сентября»)."),
            "replies": [{"label": "Отмена", "value": "отмена"}],
        }
    return {}


def _normalize_items(items: list[dict]) -> list[dict]:
    """Лёгкая канонизация полей перед сохранением импорта."""
    out = []
    for i in items:
        if not isinstance(i, dict) or not (i.get("title") or "").strip():
            continue
        try:
            st = str(i.get("start_time", "")).strip().replace(".", ":")
            en = str(i.get("end_time", "")).strip().replace(".", ":")
            if not (re.match(r"^\d{1,2}:\d{2}$", st) and re.match(r"^\d{1,2}:\d{2}$", en)):
                continue
            if int(st.split(":")[0]) > 23 or int(en.split(":")[0]) > 23:
                continue
        except (ValueError, IndexError):
            continue
        it = {
            "title": str(i["title"]).strip()[:500],
            "start_time": st, "end_time": en,
            "group_name": str(i.get("group_name", "") or "")[:100],
            "room": str(i.get("room", "") or "")[:100],
            "teacher": str(i.get("teacher", "") or "")[:200],
            "type": str(i.get("type", "lesson") or "lesson")[:20],
        }
        dow = i.get("day_of_week")
        if dow is not None:
            try:
                d = int(dow)
                if 0 <= d <= 6:
                    it["day_of_week"] = d
            except (TypeError, ValueError):
                pass
        if i.get("weeks"):
            it["weeks"] = str(i["weeks"])[:100]
        ed = str(i.get("event_date") or "")[:10]
        if ed:
            try:
                it["event_date"] = date.fromisoformat(ed).isoformat()
            except ValueError:
                pass
        out.append(it)
    return out


def _pending_from_message(message: str) -> dict:
    """Режим записи, выраженный текстом загрузки: self (умолчание) | transfer | distribute."""
    from app.services.teacher_matcher import (
        detect_distribute_all, detect_transfer_target, extract_target_teacher,
    )
    from app.services.chat_intents import extract_transfer_between
    m = (message or "").strip()
    if not m:
        return {"mode": "self"}
    if detect_distribute_all(m):
        return {"mode": "distribute"}
    src, dst = extract_transfer_between(m)
    if src and dst:
        return {"mode": "transfer", "fio": src, "to": dst}
    fio = extract_target_teacher(m)
    t = detect_transfer_target(m, fio)
    if t:
        return {"mode": "transfer", "fio": t}
    if fio:
        return {"mode": "self", "fio": fio}
    return {"mode": "self"}


async def _expand_import(imp: ScheduleImport, anchor: date, start: date, end: date) -> tuple[int, str]:
    """Развёртка weekly-шаблонов в даты; возвращает (кол-во, ошибку).

    Всегда разворачиваем от исходных распознанных занятий (source_items_json),
    а не от уже развёрнутых, — чтобы повторная смена периода была идемпотентна.
    """
    import json as _json
    raw = imp.source_items_json or imp.items_json
    try:
        items = _json.loads(raw or "[]")
    except Exception:
        items = []
    # если исходники не заполнены (старый импорт) — берём items, отфильтровав даты
    if not items:
        items = [dict(i, event_date=None) for i in _json.loads(imp.items_json or "[]")
                 if not i.get("event_date")]
    expanded = expand_items(items, first_monday=monday_of(anchor), start=start, end=end)
    if not expanded:
        return 0, "За выбранный период занятий из файла не получилось — измените даты."
    imp.items_json = json.dumps(expanded, ensure_ascii=False)
    imp.period_start = monday_of(anchor)
    imp.period_end = end
    imp.state = ImportState.READY
    return len(expanded), ""


async def _finalize_import(db: AsyncSession, user: User, imp: ScheduleImport) -> tuple[str, dict | None]:
    """Импорт в READY → предложение по отложенному требованию (pending_json)."""
    pending = {}
    try:
        pending = json.loads(imp.pending_json or "{}")
    except Exception:
        pass
    mode = pending.get("mode") or "self"
    fio = pending.get("fio") or ""
    to_fio = pending.get("to") or ""
    p, text = await chat_exec.make_import_proposal(db, user, imp, mode, fio, to_fio)
    if p is None:
        return text, None
    return text, chat_exec.proposal_public(p)


# ─── /send ────────────────────────────────────────────────────────

@router.post("/send")
async def chat_send(
    body: ChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    """SSE: детерминированные намерения раньше AI; любые записи — карточкой."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    await _store_msg(db, current_user.id, "user", message)
    imp = await _active_import(db, current_user.id)
    imp_id = imp.id if imp else None
    intent = detect_intent(message, import_state=_state_val(imp.state) if imp else "",
                           today=date.today())

    # Намерения, требующие импорта, без импорта — не намерения (уходят к AI)
    if intent and imp is None and (intent.kind in ("add_pairs", "transfer", "distribute")
                                   or intent.kind.startswith("import_")):
        intent = None

    async def generate():
        try:
            if intent is not None:
                async with DataSessionLocal() as wdb:
                    # импорт перечитываем В СВОЕЙ сессии: чужой (закрытый) объект
                    # молча теряет изменения
                    imp_w = None
                    if imp_id:
                        imp_w = (await wdb.execute(
                            select(ScheduleImport).where(ScheduleImport.id == imp_id)
                        )).scalar_one_or_none()
                    text, proposal, question = await _run_intent(wdb, current_user, intent, imp_w, message)
                    if text:
                        mid = await _store_msg(wdb, current_user.id, "assistant", text)
                    else:
                        mid = None
                payload = {"chunk": text or "", "done": True, "message_id": mid}
                if proposal:
                    payload["proposal"] = proposal
                if question:
                    payload["question"] = question
                yield _sse(payload)
                return

            # ── AI-слой ──
            system_context = await build_system_context(current_user.id)
            r = await db.execute(
                select(ChatHistory).where(ChatHistory.user_id == current_user.id)
                .order_by(ChatHistory.created_at.desc()).limit(30))
            history = list(reversed(r.scalars().all()))
            msgs = [{"role": "system", "content": system_context}]
            msgs += [{"role": h.role, "content": h.content} for h in history]

            assistant_id = await _store_msg(db, current_user.id, "assistant", "")

            provider = await create_ai_provider()
            full = ""
            async for chunk in provider.chat_stream(msgs, temperature=0.7):
                full += chunk
                yield _sse({"chunk": chunk})
                await asyncio.sleep(0)

            actions, clean_text = extract_actions(full)
            sched_acts = [a for a in actions if a.get("action") == "create_schedule"]
            note = ""
            if sched_acts and not _WHEN_RE.search(message):
                actions = [a for a in actions if a.get("action") != "create_schedule"]
                note = _IMPORT_FILE_NOTE

            display = clean_text or full
            if note:
                display += note
            async with DataSessionLocal() as wdb:
                m = (await wdb.execute(select(ChatHistory).where(ChatHistory.id == assistant_id))).scalar_one_or_none()
                if m:
                    m.content = display
                    await wdb.commit()
                proposal_pub = None
                if actions:
                    p = await chat_exec.make_actions_proposal(wdb, current_user, actions,
                                                              summary="Действия из запроса — подтвердите.")
                    if p is not None:
                        await wdb.commit()
                        proposal_pub = chat_exec.proposal_public(p)

            payload = {"chunk": "", "done": True, "message_id": assistant_id}
            if (display != full) or proposal_pub or note:
                payload["final_text"] = display
            if proposal_pub:
                payload["proposal"] = proposal_pub
            yield _sse(payload)

        except Exception as e:
            logger.exception("chat send failed")
            err = f"Ошибка: {str(e)[:300]}"
            yield _sse({"chunk": err, "done": True, "error": True})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})


async def _run_intent(db: AsyncSession, user: User, intent: Intent,
                      imp: ScheduleImport | None, message: str) -> tuple[str, dict | None, dict | None]:
    """Детерминированные ветки. Возвращает (текст ответа, proposal?, question?)."""
    today = date.today()
    k = intent.kind

    if k == "import_cancel" and imp is not None:
        imp.state = ImportState.CANCELLED
        await db.commit()
        return "Отменил. Файл остаётся в памяти — можно вернуться к нему новой загрузкой.", None, None

    if k == "import_anchor" and imp is not None and imp.state in (ImportState.ASK_PERIOD, ImportState.ASK_END):
        try:
            a = date.fromisoformat(intent.scope.get("anchor", ""))
        except ValueError:
            return "Не понял дату — напишите, например, «с 8 сентября».", None, None
        imp.period_start = monday_of(a)
        await db.commit()
        return (f"Неделя-1 теперь с {imp.period_start:%d.%m.%Y} ({DAYS[imp.period_start.weekday()]}). "
                + ("Жду дату окончания семестра." if imp.state == ImportState.ASK_END
                   else "На какую часть разложить — ближайшую неделю или семестр?"),
                None, _period_question(imp, today))

    if k in ("import_week", "import_semester_ask_end", "import_semester") and imp is not None:
        if imp.kind != ImportKind.WEEKLY:
            return "Этот файл уже с конкретными датами — период выбирать не нужно.", None, None

        if k == "import_week":
            start, end = next_week_window(today)
            if imp.period_start and imp.period_start > today:
                start, end = imp.period_start, imp.period_start + timedelta(days=6)
            n, err = await _expand_import(imp, imp.period_start or start, start, end)
            if err:
                return err, None, None
            await db.commit()
            text, proposal = await _finalize_import(db, user, imp)
            return (f"Развернул на неделю {start.strftime('%d.%m')}–{end.strftime('%d.%m')}: {n} занятий.\n{text}",
                    proposal, None)

        if k == "import_semester_ask_end":
            imp.state = ImportState.ASK_END
            if imp.period_start is None:
                imp.period_start = monday_of(today)
            await db.commit()
            return ("Семестр — хорошо. До какой даты раскладывать? Например: «до 30 декабря».",
                    None, _period_question(imp, today))

        # import_semester с датой сразу
        try:
            end = date.fromisoformat(intent.scope["end"])
        except (ValueError, KeyError):
            return "Не понял дату окончания — напишите «до 30 декабря».", None, None
        anchor = imp.period_start or monday_of(today)
        if end < anchor:
            return (f"Дата окончания ({end:%d.%m}) раньше начала семестра ({anchor:%d.%m}) — "
                    "исправьте, пожалуйста.", None, None)
        # разворачиваем от начала недели якоря, но не из прошлого: семестр «сегодня — до даты»
        start = max(monday_of(anchor), today)
        n, err = await _expand_import(imp, anchor, start, end)
        if err:
            return err, None, None
        await db.commit()
        text, proposal = await _finalize_import(db, user, imp)
        return (f"Развернул с {monday_of(anchor):%d.%m} по {end:%d.%m} ({n} занятий).\n{text}",
                proposal, None)

    if k in ("add_pairs", "transfer", "distribute") and imp is not None:
        if imp.state in (ImportState.ASK_PERIOD, ImportState.ASK_END):
            pending = {"mode": k if k != "add_pairs" else "self"}
            if intent.fio:
                pending["fio"] = intent.fio
            if intent.scope.get("to"):
                pending["to"] = intent.scope["to"]
            imp.pending_json = json.dumps(pending, ensure_ascii=False)
            await db.commit()
            return ("Сначала определимся с периодом — файл ещё ждёт ответа.\n",
                    None, _period_question(imp, today))
        # READY: remember request for future re-fires, and build proposal now
        pending = {"mode": k if k != "add_pairs" else "self"}
        if intent.fio:
            pending["fio"] = intent.fio
        if intent.scope.get("to"):
            pending["to"] = intent.scope["to"]
        imp.pending_json = json.dumps(pending, ensure_ascii=False)
        await db.commit()
        text, proposal = await _finalize_import(db, user, imp)
        if proposal is None:
            return text, None, None
        return text, proposal, None

    if k == "clear":
        p, text = await chat_exec.make_clear_proposal(db, user, message, intent.scope, intent.fio)
        if p is None:
            return text, None, None
        await db.commit()
        return text, chat_exec.proposal_public(p), None

    return "Хм, не распознал намерение — переформулируйте или спросите по-другому.", None, None


# ─── /upload ──────────────────────────────────────────────────────

@router.post("/upload")
async def chat_upload_file(
    file: UploadFile = File(...),
    message: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    """Файл расписания → ScheduleImport → вопрос периода или карточка записи.

    .xls/.xlsx — структурный парсер таблиц МЭИ; .docx — структурный парсер
    расписаний-сессий; .pdf/.txt/.doc — текстовый дамп + AI. Всё, что с
    реальными датами, идёт в календарь сразу; недельная сетка — через
    вопрос «на ближайшую неделю или на семестр».
    """
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_BYTES:
        raise HTTPException(400, detail="Файл слишком большой (макс. 10MB)")
    query = (message or "").strip()
    fname = file.filename or "файл"
    ext = _os.path.splitext(fname)[1].lower()

    try:
        items: list[dict] = []
        how = ""
        if ext in (".xls", ".xlsx"):
            items = parse_xls_schedule(file_bytes, fname)
            how = "структурный парсер Excel"
            if not items:
                txt = extract_xls_text(file_bytes, fname)
                if not txt.strip():
                    raise HTTPException(400, detail="Файл Excel не похож на расписание (не найдены группы и дни недели)")
                items = await _ai_parse(txt, query)
                how = "AI-разбор текстового дампа Excel"
        elif ext == ".docx":
            items = parse_docx_schedule(file_bytes, fname)
            how = "структурный парсер DOCX"
            if not items:
                txt = await extract_text_from_file(file_bytes, fname)
                if not txt.strip():
                    raise HTTPException(400, detail="В docx не найдено распознаваемого расписания")
                items = await _ai_parse(txt, query)
                how = "AI-разбор текста DOCX"
        else:
            txt = await extract_text_from_file(file_bytes, fname)
            if not txt.strip():
                raise HTTPException(400, detail="Не удалось извлечь текст из файла")
            items = await _ai_parse(txt, query)
            how = "AI-разбор"

        items = _normalize_items(items)
        if not items:
            raise HTTPException(400, detail="В файле не распознано ни одного занятия. "
                                            "Форматы-гаранты: таблицы .xls/.xlsx МЭИ и .docx-сессии; "
                                            "остальное — через AI, ему нужен читаемый текст.")

        # Отменяем прежний незавершённый импорт: новый файл важнее
        old = await _active_import(db, current_user.id)
        if old is not None:
            old.state = ImportState.CANCELLED

        is_dated = any(i.get("event_date") for i in items)
        kind = ImportKind.DATED if is_dated else ImportKind.WEEKLY
        today = date.today()

        imp = ScheduleImport(
            user_id=current_user.id, filename=fname, kind=kind,
            items_json=json.dumps(items, ensure_ascii=False),
            source_items_json=json.dumps(items, ensure_ascii=False),
            pending_json=json.dumps(_pending_from_message(query), ensure_ascii=False),
            state=ImportState.READY if is_dated else ImportState.ASK_PERIOD,
        )
        if is_dated:
            dates = sorted(i["event_date"] for i in items if i.get("event_date"))
            imp.period_start = date.fromisoformat(dates[0])
            imp.period_end = date.fromisoformat(dates[-1])
        else:
            imp.period_start = monday_of(today)
            # явный период прямо в сообщении загрузки?
            low = query.lower()
            if re.search(r"\b(на\s+ближайшую\s+неделю|на\s+неделю|неделю)\b", low):
                start, end = next_week_window(today)
                n, _e = await _expand_import(imp, monday_of(today), start, end)
            elif ("семестр" in low) and parse_date_loose(low, today):
                end = parse_date_loose(low, today)
                if end:
                    n, _e = await _expand_import(imp, monday_of(today), monday_of(today), end)
        db.add(imp)

        n_own = _count_for(items, current_user.full_name)
        await _store_msg(db, current_user.id, "user",
                         f"[Загружен файл: {fname}] {how}: распознано {len(items)} занятий "
                         f"({_state_val(imp.state)}). "
                         f"Содержимое файла в истории не хранится — данные берутся из сохранённого импорта.")
        await db.commit()

        if imp.state == ImportState.READY:
            text, proposal = await _finalize_import(db, user=current_user, imp=imp)
            reply = (f"Файл «{fname}»: {len(items)} занятий по датам "
                     f"{imp.period_start:%d.%m.%Y} — {imp.period_end:%d.%m.%Y}.\n{text}")
            payload: dict = {"status": "proposal" if proposal else "info",
                             "message": reply, "filename": fname,
                             "import": _import_public(imp)}
            if proposal:
                payload["proposal"] = proposal
            else:
                payload["question"] = {"text": "Можно попросить «распредели всем преподавателям» "
                                               "или «добавь пары Фамилии ко мне».", "replies": []}
            await _store_msg(db, current_user.id, "assistant", reply)
            return payload

        # вопрос о периоде
        q = _period_question(imp, today)
        hint = (f"Ваших пар в файле: {n_own}." if n_own
                else f"Ваших пар в файле не нашлось — можно «добавь пары Фамилии ко мне» или «распредели всем».")
        reply = f"Файл «{fname}»: {len(items)} занятий, {hint}\n{q['text']}"
        await _store_msg(db, current_user.id, "assistant", reply)
        return {"status": "question", "message": reply, "question": q,
                "filename": fname, "import": _import_public(imp)}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chat upload failed")
        raw = str(e)
        if "429" in raw or "rate limit" in raw.lower():
            friendly = "Лимит запросов к AI-провайдеру исчерпан — попробуйте позже или смените модель в настройках."
        elif "401" in raw or "invalid_api_key" in raw.lower():
            friendly = "AI-провайдер отклонил API-ключ. Проверьте ключ в настройках AI."
        else:
            friendly = f"Ошибка обработки файла: {raw[:300]}"
        await _store_msg(db, current_user.id, "assistant", friendly)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=friendly)


async def _ai_parse(text: str, query: str) -> list[dict]:
    prov = await create_ai_provider()
    truncated = text[:15000] + ("\n\n[Текст обрезан]" if len(text) > 15000 else "")
    parsed = await prov.parse_schedule_all(truncated, user_query=query)
    return parsed.get("items", []) or []


def _count_for(items: list[dict], who: str) -> int:
    from app.services.teacher_matcher import names_match
    return sum(1 for i in items if names_match(i.get("teacher", ""), who or ""))


def _import_public(imp: ScheduleImport) -> dict:
    return {"id": imp.id, "filename": imp.filename,
            "kind": imp.kind.name if hasattr(imp.kind, "name") else str(imp.kind),
            "state": imp.state.name if hasattr(imp.state, "name") else str(imp.state),
            "period_start": imp.period_start.isoformat() if imp.period_start else None,
            "period_end": imp.period_end.isoformat() if imp.period_end else None}


# ─── /confirm /reject ─────────────────────────────────────────────

@router.post("/confirm")
async def chat_confirm(
    body: ConfirmBody,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    p = (await db.execute(select(Proposal).where(Proposal.id == body.proposal_id))).scalar_one_or_none()
    if p is None or p.user_id != current_user.id:
        raise HTTPException(404, detail="Предложение не найдено")
    if p.status != ProposalStatus.PENDING:
        return {"ok": False, "report": "Это предложение уже обработано."}

    report = await chat_exec.apply_proposal(db, current_user, p, body.selected)
    p.status = ProposalStatus.APPLIED
    await db.commit()
    await _store_msg(db, current_user.id, "assistant", report, ctx_type="action")
    return {"ok": True, "report": report, "proposal_id": p.id}


@router.post("/reject")
async def chat_reject(
    body: RejectBody,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    p = (await db.execute(select(Proposal).where(Proposal.id == body.proposal_id))).scalar_one_or_none()
    if p is None or p.user_id != current_user.id:
        raise HTTPException(404, detail="Предложение не найдено")
    if p.status == ProposalStatus.PENDING:
        p.status = ProposalStatus.REJECTED
        await db.commit()
        await _store_msg(db, current_user.id, "assistant", "Отменено.", ctx_type="action")
    return {"ok": True}


# ─── /history ─────────────────────────────────────────────────────

@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(ChatHistory).where(ChatHistory.user_id == current_user.id)
        .order_by(ChatHistory.created_at.desc()).limit(limit))
    messages = [ChatMessageOut.model_validate(m) for m in reversed(r.scalars().all())]

    pending = (await db.execute(
        select(Proposal).where(Proposal.user_id == current_user.id,
                               Proposal.status == ProposalStatus.PENDING)
        .order_by(Proposal.created_at.desc()).limit(1))).scalars().first()
    imp = await _active_import(db, current_user.id)
    question = _period_question(imp, date.today()) if (imp and imp.state in
                                                       (ImportState.ASK_PERIOD, ImportState.ASK_END)) else None
    return {"messages": messages,
            "pending_proposal": chat_exec.proposal_public(pending) if pending else None,
            "question": question or None,
            "import": _import_public(imp) if imp else None}
