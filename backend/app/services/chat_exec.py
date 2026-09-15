"""Заземление намерений на БД и исполнение предложений (Proposals).

Принцип: клиент никогда не присылает список действий — только proposal_id.
Действия строятся на сервере (из AI-intents или детерминированных намерений),
заземляются на реальные строки БД (id), предлагаются карточкой, применяются
по подтверждению. Права проверяются и при построении, и при исполнении.
"""
import json
import logging
import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_models import User
from app.models.data_models import (
    Proposal, ProposalKind, ProposalStatus, Schedule, ScheduleImport,
    ScheduleSource, ScheduleType, Task,
)
from app.services.schedule_dedup import DuplicateTracker
from app.services.teacher_matcher import (
    clean_teacher_name, find_user_by_teacher_name, names_match,
)

logger = logging.getLogger(__name__)

DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MAX_CARD_ITEMS = 30


def _parse_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _parse_time(s) -> time | None:
    try:
        parts = str(s).strip().replace(".", ":").split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _is_manager(user: User) -> bool:
    return user.role in ("admin", "manager")


def proposal_public(p: Proposal) -> dict:
    """JSON-карточка для клиента."""
    payload = json.loads(p.payload_json or "{}")
    out = {
        "id": p.id,
        "kind": p.kind.name if hasattr(p.kind, "name") else str(p.kind),
        "summary": payload.get("summary", ""),
        "items": payload.get("rows_public", [])[:MAX_CARD_ITEMS],
        "total": payload.get("total", len(payload.get("rows_public", []))),
    }
    if payload.get("news"):
        out["news"] = payload["news"]
    return out


async def _expire_stale_pending(db: AsyncSession, user_id: str) -> None:
    """Живой может быть только один хвост: новая карточка снимает статус
    со всех прежних неподтверждённых (иначе /history показывает старую)."""
    from sqlalchemy import update
    await db.execute(
        update(Proposal)
        .where(Proposal.user_id == user_id, Proposal.status == ProposalStatus.PENDING)
        .values(status=ProposalStatus.REJECTED)
    )


# ─── Заземление AI-действий ───────────────────────────────────────

async def _owner_scope(db, user, p: dict):
    """Возвращает (owner_ids, error). teacher_name в params — только для менеджера."""
    tname = (p.pop("teacher_name", None) or "").strip()
    if not tname:
        return [user.id], ""
    if not _is_manager(user):
        return None, "Только управляющий может работать с чужим календарём"
    tu = await find_user_by_teacher_name(db, tname)
    if not tu:
        return None, f"Преподаватель «{tname}» не найден в системе"
    return [tu.id], ""


def _sched_desc(s: Schedule, owner_name: str = "") -> str:
    when = (s.event_date.strftime("%d.%m") if s.event_date
            else f"{DAYS_SHORT[s.day_of_week]} (каждую неделю)")
    bits = [when, s.start_time.strftime("%H:%M")]
    if s.group_name:
        bits.append(f"гр. {s.group_name}")
    if owner_name:
        bits.append(f"— {owner_name}")
    return f"«{s.title[:60]}» " + ", ".join(bits)


async def ground_actions(db: AsyncSession, user: User, actions: list[dict]) -> tuple[list[dict], list[str]]:
    """AI-действия → действия с конкретными id (или понятные ошибки).

    Возвращает (grounded, notes). Одно действие на неопределённого получателя
    может развернуться в N (по каждому совпадению — своя строка карточки).
    """
    grounded: list[dict] = []
    notes: list[str] = []

    for a in actions:
        act = a.get("action", "")
        p = dict(a.get("params") or {})
        desc = a.get("description") or ""

        if act == "create_schedule":
            owner_ids, err = await _owner_scope(db, user, p)
            if not owner_ids:
                grounded.append({"action": act, "params": {}, "description": f"⚠️ {err}", "always_fails": err})
                continue
            if len(owner_ids) == 1 and owner_ids[0] != user.id:
                p["_owner_id"] = owner_ids[0]
            if p.get("date") and not _parse_date(p.get("date")):
                p.pop("date")
            grounded.append({"action": act, "params": p, "description": desc or _describe(p)})
            continue

        if act == "create_task":
            owner_ids, err = await _owner_scope(db, user, p)
            if not owner_ids:
                grounded.append({"action": act, "params": {}, "description": f"⚠️ {err}", "always_fails": err})
                continue
            if len(owner_ids) == 1 and owner_ids[0] != user.id:
                p["_owner_id"] = owner_ids[0]
            grounded.append({"action": act, "params": p, "description": desc or _describe(p)})
            continue

        if act in ("update_schedule", "delete_schedule"):
            target_owner = p.pop("target_teacher_name", None)
            owner_ids, err = await _owner_scope(db, user, p)
            if not owner_ids:
                grounded.append({"action": act, "params": {}, "description": f"⚠️ {err}", "always_fails": err})
                continue

            needle = (p.get("title") or p.get("id") or "").strip()
            rows = []
            if needle and len(needle) == 36 and "-" in needle:
                s = await db.get(Schedule, needle)
                if s and (s.user_id in owner_ids or _can_touch(user, s.user_id)):
                    rows = [s]
            elif needle:
                conds = select(Schedule).where(Schedule.user_id.in_(owner_ids))
                cand = (await db.execute(conds.where(Schedule.title.ilike(needle)))).scalars().all()
                if not cand:
                    cand = (await db.execute(conds.where(Schedule.title.ilike(f"%{needle}%")))).scalars().all()
                # необязательные фильтры по дате/дню из params
                fd = _parse_date(p.get("date"))
                fw = p.get("day_of_week")
                def match(s):
                    if fd and s.event_date and s.event_date != fd:
                        return False
                    if fw is not None and (s.event_date.weekday() if s.event_date else s.day_of_week) != int(fw):
                        return False
                    return True
                rows = [s for s in cand if match(s)]

            if not rows:
                grounded.append({"action": act, "params": {"title": needle},
                                 "description": f"⚠️ Пара «{needle[:40]}» не найдена",
                                 "always_fails": "не найдена"})
                continue
            if len(rows) > 1:
                notes.append(f"По запросу «{needle[:40]}» найдено {len(rows)} пар — отметьте нужные.")
            owner_names = {}
            if len(owner_ids) > 1 or owner_ids[0] != user.id:
                for oid in {s.user_id for s in rows}:
                    ou = await db.get(User, oid)
                    owner_names[oid] = ou.full_name if ou else ""
            for s in rows:
                pp = dict(p)
                pp.pop("title", None)
                pp["id"] = s.id
                if target_owner:
                    pp["teacher_name"] = target_owner
                d = f"{'Удалить' if act == 'delete_schedule' else 'Изменить'} {_sched_desc(s, owner_names.get(s.user_id, ''))}"
                grounded.append({"action": act, "params": pp,
                                 "description": desc if len(rows) == 1 and desc else d})
            continue

        if act in ("update_task", "delete_task", "update_task_status"):
            owner_ids, err = await _owner_scope(db, user, p)
            if not owner_ids:
                grounded.append({"action": act, "params": {}, "description": f"⚠️ {err}", "always_fails": err})
                continue
            needle = (p.get("title") or p.get("id") or "").strip()
            if needle and len(needle) == 36 and "-" in needle:
                rows = [t for t in [(await db.get(Task, needle))] if t and t.user_id in owner_ids]
            else:
                conds = select(Task).where(Task.user_id.in_(owner_ids))
                rows = (await db.execute(conds.where(Task.title.ilike(f"%{needle}%")))).scalars().all()
            if not rows:
                grounded.append({"action": act, "params": {"title": needle},
                                 "description": f"⚠️ Задача «{needle[:40]}» не найдена",
                                 "always_fails": "не найдена"})
                continue
            for t in rows:
                pp = dict(p)
                pp.pop("title", None)
                pp["id"] = t.id
                grounded.append({"action": act, "params": pp,
                                 "description": f"Задача «{t.title[:60]}»"
                                                + (" — удалить" if act == "delete_task"
                                                   else f" → статус {p.get('status')}" if act == "update_task_status"
                                                   else " — изменить")})
            continue

        grounded.append({"action": act, "params": p, "description": desc or f"Действие {act}"})

    return grounded, notes


def _describe(p: dict) -> str:
    bits = []
    if p.get("title"):
        bits.append(f"«{p['title'][:60]}»")
    if p.get("date"):
        bits.append(str(p["date"])[:10])
    if isinstance(p.get("day_of_week"), int) and 0 <= p["day_of_week"] < 7:
        bits.append(DAYS_SHORT[p["day_of_week"]])
    if p.get("start_time"):
        bits.append(str(p["start_time"]))
    return "Добавить: " + " ".join(bits) if bits else "Действие"


# ─── Построение предложений ───────────────────────────────────────

async def make_actions_proposal(db: AsyncSession, user: User, actions: list[dict],
                                summary: str = "") -> Proposal | None:
    grounded, _notes = await ground_actions(db, user, actions)
    if not grounded:
        return None
    rows_public = [{"text": a.get("description") or _describe(a.get("params", {})),
                    "kind": a.get("action")} for a in grounded]
    await _expire_stale_pending(db, user.id)
    p = Proposal(
        user_id=user.id, kind=ProposalKind.ACTIONS,
        payload_json=json.dumps({"summary": summary, "actions": grounded,
                                 "rows_public": rows_public, "total": len(grounded)},
                                ensure_ascii=False),
    )
    db.add(p)
    await db.flush()
    return p


async def make_import_proposal(db: AsyncSession, user: User, imp: ScheduleImport,
                               mode: str, fio: str = "", to_fio: str = "") -> tuple[Proposal | None, str]:
    """mode: 'self' | 'transfer' | 'distribute'. Возвращает (proposal, текст-ответ).

    'transfer' с to_fio: занятия ФИО из файла (fio) кладутся в календарь
    ДРУГОГО пользователя (to_fio) — «перенеси пары Федуловой к Шапуленковой».
    Без to_fio — прежнее поведение: пары X в аккаунт самого X.
    """
    items = json.loads(imp.items_json or "[]")
    if not items:
        return None, "Импорт пуст — загрузите файл заново."

    # weekly уже развёрнут в даты машиной состояний (state=READY ⇒ event_date есть)
    undated = [i for i in items if not i.get("event_date")]
    if undated:
        return None, "Импорт ещё не развёрнут по датам — выберите период."

    rows: list[dict] = []          # {owner_id, owner_name, item}
    no_account: list[str] = []
    own_missing = ""
    xfer_note = ""

    if mode == "self":
        who = fio or user.full_name
        picked = [i for i in items if names_match(i.get("teacher", ""), who)]
        if not picked:
            own_missing = who
        else:
            rows = [{"owner_id": user.id, "owner_name": user.full_name, "item": i} for i in picked]

    elif mode == "transfer":
        src = fio or to_fio                      # чьи пары берём из файла
        dst = to_fio or fio                      # кому в календарь (по умолчанию себе)
        picked = [i for i in items if names_match(i.get("teacher", ""), src)]
        if not names_match(dst, user.full_name) and not _is_manager(user):
            return None, ("Переносить занятия в календарь другого преподавателя может только "
                          "административная учётная запись. «К себе» — можно и учителю.")
        tu = await find_user_by_teacher_name(db, dst)
        if tu is None:
            return None, (f"Пар «{src}» в файле найдено {len(picked)}, но учётной записи "
                          f"«{dst}» нет — создайте её (админ → Пользователи) "
                          "или уточните ФИО. Ничего не записано.")
        if not picked:
            return None, f"В файле пар для «{src}» не нашлось — календарь {tu.full_name} не изменён."
        rows = []
        for i in picked:
            # помечаем замещение в названии, если переносим от ДРУГОГО преподавателя
            src_t = clean_teacher_name(i.get("teacher", "")) or src
            if not names_match(src_t, tu.full_name):
                i = {**i, "title": f"{(i.get('title') or '').strip()} · зам. {src_t}"}
            rows.append({"owner_id": tu.id, "owner_name": tu.full_name, "item": i})
        if to_fio and not names_match(src, dst):
            xfer_note = f"Перенос: «{src}» → {tu.full_name}."

    elif mode == "distribute":
        by_teacher: dict[str, list[dict]] = {}
        for i in items:
            tn = clean_teacher_name(i.get("teacher", ""))
            if tn:
                by_teacher.setdefault(tn.lower(), []).append(i)
        for tname, t_items in by_teacher.items():
            tu = await find_user_by_teacher_name(db, tname)
            if tu is None:
                no_account.append(tname)
                continue
            rows.extend({"owner_id": tu.id, "owner_name": tu.full_name, "item": i} for i in t_items)
        if not rows:
            return None, ("Ни у одного преподавателя из файла нет учётной записи — "
                          f"без аккаунта {len(no_account)} человек. Ничего не записано.")
    else:
        return None, "Неизвестный режим импорта."

    if not rows:
        hint = ""
        if mode == "self":
            hint = (f" В файле нет пар для «{own_missing}». Подсказки: «добавь пары Федуловой ко мне» "
                    "(замещение), «распредели всем преподавателям».")
        return None, "Нечего добавлять." + hint

    # группировка для карточки
    per_owner: dict[str, list[dict]] = {}
    for r in rows:
        per_owner.setdefault(r["owner_name"], []).append(r)
    lines = []
    for owner_name, rs in list(per_owner.items()):
        first = rs[0]["item"]
        lines.append(f"{owner_name} — {len(rs)} " + ("пар" if len(rs) != 1 else "пара"))
    summary = f"Файл «{imp.filename}»: {len(rows)} записей на {len(per_owner)} преподават."
    if xfer_note:
        summary = xfer_note + " " + summary
    rows_public = []
    for r in rows[:MAX_CARD_ITEMS]:
        i = r["item"]
        d = _parse_date(i.get("event_date"))
        when = f"{d.strftime('%d.%m')} {DAYS_SHORT[d.weekday()]}" if d else "?"
        rows_public.append({"text": f"{r['owner_name']}: {when} {i.get('start_time','')} «{str(i.get('title',''))[:45]}» {i.get('group_name','')}".strip(),
                            "kind": "import"})
    await _expire_stale_pending(db, user.id)
    p = Proposal(
        user_id=user.id, kind=ProposalKind.IMPORT_PLAN,
        payload_json=json.dumps({
            "summary": summary, "import_id": imp.id,
            "rows": [{"owner_id": r["owner_id"], "item": r["item"]} for r in rows],
            "rows_public": rows_public, "total": len(rows),
            "no_account": no_account[:20],
        }, ensure_ascii=False),
    )
    db.add(p)
    await db.flush()
    text = f"Готово к записи: {summary}."
    if no_account:
        text += f" ⚠️ Без учётной записи {len(no_account)} преподавателей (не записывается)."
    return p, text


async def make_clear_proposal(db: AsyncSession, user: User, text: str,
                              scope: dict, target_fio: str = "") -> tuple[Proposal | None, str]:
    """«Очисти календарь [у ФИО] [дн.]» → карточка с точным списком id."""
    owner_ids, owner_label = [user.id], ""
    if target_fio:
        if not _is_manager(user):
            return None, "Очищать чужие календари может только управляющий или админ."
        tu = await find_user_by_teacher_name(db, target_fio)
        if tu is None:
            return None, f"Преподаватель «{target_fio}» не найден — очистка не выполнена."
        owner_ids = [tu.id]
        owner_label = tu.full_name

    want_tasks = bool(re.search(r"(задач|заметк|напомин|все\s+и\s+всяч)", text, re.IGNORECASE))
    want_sched = bool(re.search(r"(пар|расписани|календар|заняти|вс[юёе])", text, re.IGNORECASE)) or not want_tasks

    def day_match(d: date | None) -> bool:
        if d is None:
            return True
        frm, to, wd = scope.get("from"), scope.get("to"), scope.get("weekday")
        if frm:
            return _parse_date(frm) <= d <= _parse_date(to)
        if wd is not None:
            return d.weekday() == int(wd)
        return True

    sched_rows: list[Schedule] = []
    if want_sched:
        all_s = (await db.execute(select(Schedule).where(Schedule.user_id.in_(owner_ids)))).scalars().all()
        for s in all_s:
            if s.event_date:
                if day_match(s.event_date):
                    sched_rows.append(s)
            else:  # шаблон: попадает, если его день недели входит в диапазон/выбран
                if scope.get("weekday") is not None:
                    if s.day_of_week == int(scope["weekday"]):
                        sched_rows.append(s)
                elif scope.get("from"):
                    frm, to = _parse_date(scope["from"]), _parse_date(scope["to"])
                    span_wd = {(frm + timedelta(days=k)).weekday() for k in range((to - frm).days + 1)} \
                        if frm and to else set()
                    if s.day_of_week in span_wd:
                        sched_rows.append(s)
                else:
                    sched_rows.append(s)

    task_rows: list[Task] = []
    if want_tasks:
        all_t = (await db.execute(select(Task).where(Task.user_id.in_(owner_ids)))).scalars().all()
        for t in all_t:
            if t.due_date:
                if day_match(t.due_date):
                    task_rows.append(t)
            elif not scope.get("from") and scope.get("weekday") is None:
                task_rows.append(t)

    total = len(sched_rows) + len(task_rows)
    if total == 0:
        return None, "Нечего удалять — под запрос не попала ни одна запись."

    rows_public = [{"text": _sched_desc(s, owner_label), "kind": "clear"}
                   for s in sched_rows[:MAX_CARD_ITEMS]]
    rows_public += [{"text": f"Задача «{t.title[:60]}»", "kind": "clear"} for t in task_rows[:MAX_CARD_ITEMS]]
    if not scope:
        scope_txt = "полностью"
    elif scope.get("weekday") is not None:
        scope_txt = DAYS_SHORT[int(scope["weekday"])]
    elif scope.get("from"):
        f, tt = _parse_date(scope["from"]), _parse_date(scope["to"])
        scope_txt = f"{f.strftime('%d.%m')}–{tt.strftime('%d.%m.%Y')}" if f and tt else "по датам"
    else:
        scope_txt = ""
    await _expire_stale_pending(db, user.id)
    p = Proposal(
        user_id=user.id, kind=ProposalKind.CLEAR,
        payload_json=json.dumps({
            "summary": f"Удалить {len(sched_rows)} пар и {len(task_rows)} задач ({scope_txt})",
            "sched_ids": [s.id for s in sched_rows],
            "task_ids": [t.id for t in task_rows],
            "rows_public": rows_public, "total": total,
        }, ensure_ascii=False),
    )
    db.add(p)
    await db.flush()
    return p, f"Подтвердите: будет удалено {len(sched_rows)} пар и {len(task_rows)} задач ({scope_txt})."


# ─── Публикация новостей из чата ──────────────────────────────────

NEWS_REFUSAL = ("Публиковать новости может только административная учётная запись. "
                "Читать их можно во вкладке «Новости».")
NEWS_AI_FAIL = ("AI не смог подготовить скорректированный вариант — новость НЕ опубликована. "
                "Проверьте настройки AI и повторите, либо опубликуйте новость "
                "во вкладке «Новости».")
NEWS_AI_TIMEOUT = 60.0


def _extract_json_obj(s: str) -> dict | None:
    s = (s or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) and (d.get("text") or d.get("title")) else None


async def _ai_rewrite_news(text: str) -> dict | None:
    """Вариант AI: {'title':..., 'text':...} или None при любом сбое."""
    import asyncio
    from app.services.ai_service import create_ai_provider
    system = (
        "Ты — редактор новостей учебного отдела инженерного факультета. "
        "Отредактируй текст объявления для ленты новостей: исправь ошибки и "
        "опечатки, сделай формулировки яснее и вежливее, СОХРАНИ все факты, "
        "даты, имена и смысл. Не добавляй того, чего не было. Верни ТОЛЬКО JSON: "
        '{"title": "короткий заголовок до 60 знаков", "text": "отредактированный текст"}'
    )
    try:
        prov = await create_ai_provider()
        chunks: list[str] = []

        async def _collect() -> None:
            async for ch in prov.chat_stream(
                    [{"role": "system", "content": system},
                     {"role": "user", "content": text}], temperature=0.4):
                chunks.append(ch)

        await asyncio.wait_for(_collect(), timeout=NEWS_AI_TIMEOUT)
        return _extract_json_obj("".join(chunks))
    except Exception as e:  # нет ключа, таймаут, мусор в ответе
        logger.warning("AI rewrite news failed: %s", e)
        return None


async def make_news_proposal(db: AsyncSession, user: User, text: str,
                             draft_id: str = "", image_names: list[str] | None = None
                             ) -> tuple[Proposal | None, str]:
    """Карточка «опубликовать новость»: вариант автора и/или вариант AI."""
    from app.services import news_store
    if not _is_manager(user):
        return None, NEWS_REFUSAL
    image_names = [n for n in (image_names or []) if news_store.safe_name(n)]
    text = (text or "").strip()[:20000]
    if not text and not image_names:
        return None, ("Что публикуем? Напишите текст после «опубликуй новость —» "
                      "(и можете прикрепить картинку 📎).")

    # сносим черновики картинок прежних неподтверждённых карточек этого юзера
    old = (await db.execute(
        select(Proposal).where(Proposal.user_id == user.id,
                               Proposal.kind == ProposalKind.NEWS,
                               Proposal.status == ProposalStatus.PENDING)
    )).scalars().all()
    for op in old:
        try:
            d = json.loads(op.payload_json or "{}").get("news", {}).get("draft_id", "")
        except json.JSONDecodeError:
            d = ""
        if d:
            news_store.delete_draft(d)

    ai: dict | None = None
    if text:
        ai = await _ai_rewrite_news(text)
        if ai is None:
            if draft_id:
                news_store.delete_draft(draft_id)
            return None, NEWS_AI_FAIL

    news = {
        "title_user": "",
        "text_user": text,
        "title_ai": str((ai or {}).get("title", ""))[:200],
        "text_ai": str((ai or {}).get("text", ""))[:20000],
        "draft_id": draft_id,
        "image_names": image_names,
        "images": [news_store.draft_url(draft_id, n) for n in image_names] if draft_id else [],
    }
    summary = (f"Новость: «{text[:60] or 'только картинки'}»"
               + (f" · {len(image_names)} фото" if image_names else "")
               + " — выберите вариант публикации.")
    await _expire_stale_pending(db, user.id)
    p = Proposal(user_id=user.id, kind=ProposalKind.NEWS,
                 payload_json=json.dumps({"summary": summary, "news": news},
                                         ensure_ascii=False))
    db.add(p)
    await db.commit()
    answer = ("Подготовил новость. AI предложил свою редакцию — "
              "на карточке выберите: опубликовать ваш текст или вариант AI.")
    if not text:
        answer = "Подготовил новость с картинками — подтверждайте публикацию."
    return p, answer


# ─── Исполнение ───────────────────────────────────────────────────

async def apply_proposal(db: AsyncSession, user: User, p: Proposal,
                         selected: list[int] | None) -> str:
    """Возвращает человекочитаемый отчёт. selected — индексы строк карточки
    (None = всё)."""
    payload = json.loads(p.payload_json or "{}")
    kind = p.kind

    if kind == ProposalKind.ACTIONS:
        from app.services.chat_actions import execute_actions
        actions = payload.get("actions", [])
        chosen = [a for i, a in enumerate(actions) if selected is None or i in selected]
        results = await execute_actions(user, chosen)
        ok = sum(1 for r in results if r["ok"])
        lines = [f"{'✅' if r['ok'] else '❌'} {r['message']}" for r in results]
        report = f"Выполнено {ok} из {len(results)}.\n" + "\n".join(lines[:20])
        return report

    if kind == ProposalKind.IMPORT_PLAN:
        rows = payload.get("rows", [])
        chosen = [r for i, r in enumerate(rows) if selected is None or i in selected]
        tracker = DuplicateTracker()
        per_owner: dict[str, list[int, int]] = {}
        added_total = skipped = bad = 0
        for r in chosen:
            owner_id = r["owner_id"]
            await tracker.prime(db, owner_id)
            i = r["item"]
            start = _parse_time(i.get("start_time", ""))
            end = _parse_time(i.get("end_time", ""))
            t = _parse_date(i.get("event_date"))
            title = (i.get("title") or "").strip()
            if not (start and end and title):
                bad += 1
                continue
            dow = t.weekday() if t else int(i.get("day_of_week", 0) or 0)
            cand = {"title": title, "day_of_week": dow,
                    "start_time": start.strftime("%H:%M"), "end_time": end.strftime("%H:%M"),
                    "group_name": i.get("group_name", ""), "event_date": i.get("event_date", "")}
            if tracker.is_duplicate(owner_id, cand):
                skipped += 1
                continue
            db.add(Schedule(
                user_id=owner_id, title=title[:500], day_of_week=dow,
                start_time=start, end_time=end,
                group_name=(i.get("group_name") or "")[:100],
                room=(i.get("room") or "")[:100],
                type=_map_type(i.get("type")),
                source=ScheduleSource.PDF_IMPORT if owner_id == user.id or not _is_manager(user)
                       else ScheduleSource.MANAGER,
                created_by=user.id, event_date=t,
            ))
            st = per_owner.setdefault(r.get("owner_name") or owner_id, [0, 0])
            st[0] += 1
            added_total += 1
        # импорт помечаем применённым
        imp = await db.get(ScheduleImport, payload.get("import_id", ""))
        if imp is not None:
            imp.state = imp.state.__class__.APPLIED
        await db.commit()
        parts = [f"{name}: +{a}" for name, (a, _s) in per_owner.items()]
        report = f"Добавлено {added_total} пар." + (f" Пропущено дублей: {skipped}." if skipped else "")
        if bad:
            report += f" Пропущено некорректных записей: {bad}."
        if len(per_owner) > 1:
            report += "\n" + "; ".join(parts[:12])
        return report

    if kind == ProposalKind.CLEAR:
        sched_ids = payload.get("sched_ids", [])
        task_ids = payload.get("task_ids", [])
        flat = [("s", i) for i in sched_ids] + [("t", i) for i in task_ids]
        chosen = [x for idx, x in enumerate(flat) if selected is None or idx in selected]
        nd = nt = 0
        for typ, oid in chosen:
            if typ == "s":
                s = await db.get(Schedule, oid)
                if s and _can_touch(user, s.user_id):
                    await db.delete(s)
                    nd += 1
            else:
                t = await db.get(Task, oid)
                if t and _can_touch(user, t.user_id):
                    await db.delete(t)
                    nt += 1
        await db.commit()
        return f"Удалено: пар {nd}, задач {nt}."

    if kind == ProposalKind.NEWS:
        from app.models.data_models import NewsItem
        from app.services import news_store
        if not _is_manager(user):
            return NEWS_REFUSAL
        news = payload.get("news") or {}
        use_ai = bool(selected) and 1 in selected and bool(news.get("text_ai"))
        if use_ai:
            body = news.get("text_ai", "")
            title = news.get("title_ai", "")
        else:
            body = news.get("text_user", "")
            # у авторского текста заголовка нет — берём заголовок, предложенный AI
            title = news.get("title_ai", "")
        if not body.strip() and not news.get("image_names"):
            return "Публиковать нечего: и текст, и картинки пусты."
        n = NewsItem(title=title[:200], body=body[:20000],
                     author_id=user.id, author_name=user.full_name)
        db.add(n)
        await db.flush()
        names: list[str] = []
        if news.get("draft_id") and news.get("image_names"):
            names = news_store.move_draft_to_news(news["draft_id"], n.id,
                                                  news["image_names"])
        n.images_json = json.dumps(names, ensure_ascii=False)
        await db.commit()
        return ("✅ Новость опубликована ("
                + ("вариант AI" if use_ai else "ваш вариант")
                + (f", фото: {len(names)}" if names else "") + ").")

    return "Предложение неизвестного типа."


def cleanup_news_draft(p: Proposal) -> None:
    """При отклонении карточки NEWS черновик картинок больше не нужен."""
    if p.kind != ProposalKind.NEWS:
        return
    try:
        from app.services import news_store
        draft = json.loads(p.payload_json or "{}").get("news", {}).get("draft_id", "")
    except json.JSONDecodeError:
        draft = ""
    if draft:
        news_store.delete_draft(draft)


def _can_touch(user: User, owner_id: str) -> bool:
    return user.id == owner_id or _is_manager(user)


def _map_type(v) -> ScheduleType:
    s = str(v or "").lower()
    if s in ("meeting", "собрание", "встреча", "мероприятие"):
        return ScheduleType.MEETING
    if s in ("other", "другое"):
        return ScheduleType.OTHER
    return ScheduleType.LESSON
