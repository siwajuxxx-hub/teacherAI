import json
import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_data_session, DataSessionLocal
from app.models.data_models import ChatHistory, Schedule, ScheduleType, ScheduleSource
from app.models.auth_models import User, UserRole
from app.schemas.data_schemas import ChatMessageRequest, ChatMessageOut
from app.security import get_current_user, require_teacher_or_above, require_admin_or_manager
from app.services.ai_service import create_ai_provider, build_system_context
from app.services.file_parser import extract_text_from_file
from app.services.xls_schedule_parser import parse_xls_schedule, extract_xls_text
from app.services.chat_actions import extract_actions, execute_actions, actions_to_public
from app.services.schedule_dedup import DuplicateTracker
from app.services.teacher_matcher import (
    find_user_by_teacher_name, get_all_teachers,
    clean_teacher_name, detect_distribute_all, extract_target_teacher, names_match,
)

router = APIRouter(prefix="/api/chat", tags=["Чат"])


def _parse_time(t: str):
    from datetime import time
    parts = t.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


@router.post("/send")
async def chat_send(
    body: ChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    """Отправка сообщения в чат с SSE-стримингом ответа."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сообщение не может быть пустым")

    user_msg = ChatHistory(user_id=current_user.id, role="user", content=message)
    db.add(user_msg)
    await db.commit()

    system_context = await build_system_context(current_user.id)

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == current_user.id)
        .order_by(ChatHistory.created_at.desc())
        .limit(30)
    )
    history = list(reversed(result.scalars().all()))

    messages = [{"role": "system", "content": system_context}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})

    assistant_msg = ChatHistory(user_id=current_user.id, role="assistant", content="")
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)
    assistant_id = assistant_msg.id

    async def generate():
        full_response = ""
        try:
            provider = await create_ai_provider()
            async for chunk in provider.chat_stream(messages, temperature=0.7):
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                await asyncio.sleep(0)

            async with DataSessionLocal() as save_db:
                result = await save_db.execute(select(ChatHistory).where(ChatHistory.id == assistant_id))
                msg = result.scalar_one_or_none()
                if msg:
                    msg.content = full_response
                    await save_db.commit()

            # Извлекаем предложенные действия (выполняет их пользователь после подтверждения)
            # user_message передаём как страховку: если AI забыл блок actions,
            # но пользователь явно просил создать задачу — она не потеряется.
            actions, clean_text = extract_actions(full_response, user_message=message)
            if actions and clean_text and clean_text != full_response:
                async with DataSessionLocal() as save_db:
                    result = await save_db.execute(select(ChatHistory).where(ChatHistory.id == assistant_id))
                    msg = result.scalar_one_or_none()
                    if msg:
                        msg.content = clean_text
                        await save_db.commit()

            payload = {'chunk': '', 'done': True, 'message_id': assistant_id}
            if actions:
                payload['actions'] = actions_to_public(actions)
                # Отдаём текст без служебного блока, чтобы он не светился в интерфейсе
                if clean_text:
                    payload['final_text'] = clean_text
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            error_text = f"Ошибка AI: {str(e)}"
            async with DataSessionLocal() as save_db:
                result = await save_db.execute(select(ChatHistory).where(ChatHistory.id == assistant_id))
                msg = result.scalar_one_or_none()
                if msg:
                    msg.content = error_text
                    await save_db.commit()
            yield f"data: {json.dumps({'chunk': error_text, 'error': True})}\n\n"

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/upload")
async def chat_upload_file(
    file: UploadFile = File(...),
    message: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    """Загрузка файла + AI-парсинг с тремя режимами:

    1. Без запроса → пары текущего преподавателя → в его календарь
    2. Запрос «добавь пары ФАМИЛИЯ» → пары того преподавателя → в календарь текущего пользователя
    3. Запрос «добавь всем преподавателям» (manager/admin) → распределяет ВСЕ пары по преподавателям
    """
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой (макс. 10MB)")

    query = message.strip() if message and message.strip() else ""

    try:
        # 1. Извлекаем содержимое.
        # Excel-расписание (.xls/.xlsx) разбирается СТРУКТУРНО — таблицы МЭИ
        # (дни × группы × ячейки «лк/лб/у ФИО, ауд») парсятся детерминированно,
        # без AI: точнее, быстрее и бесплатно. Если структура не распознана —
        # откат на текстовый дамп + AI-парсинг.
        import os as _os
        ext = _os.path.splitext(file.filename or "")[1].lower()
        xls_items = None
        extracted_text = ""
        if ext in (".xls", ".xlsx"):
            xls_items = parse_xls_schedule(file_bytes, file.filename or "")
            if not xls_items:
                extracted_text = extract_xls_text(file_bytes, file.filename or "")
            if not xls_items and not extracted_text.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Файл Excel не похож на расписание (не найдены группы и дни недели)",
                )
        else:
            extracted_text = await extract_text_from_file(file_bytes, file.filename or "")
            if not extracted_text:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось извлечь текст")

        truncated_text = extracted_text[:15000]
        if len(extracted_text) > 15000:
            truncated_text += "\n\n[Текст обрезан]"
        # 2. Сохраняем в историю чата
        if xls_items is not None:
            user_text = f"[Загружен файл: {file.filename}]\nСтруктурный парсер Excel: распознано {len(xls_items)} занятий."
        elif query:
            user_text = f"[Загружен файл: {file.filename}]\nЗапрос: {query}\n\nСодержимое файла:\n{truncated_text}"
        else:
            user_text = f"[Загружен файл: {file.filename}]\n\nСодержимое файла:\n{truncated_text}"
        if query and xls_items is not None:
            user_text = f"[Загружен файл: {file.filename}]\nЗапрос: {query}\nСтруктурный парсер Excel: распознано {len(xls_items)} занятий."

        db.add(ChatHistory(
            user_id=current_user.id, role="user", content=user_text,
            context_type="file", context_id=str(uuid.uuid4()),
        ))
        await db.commit()

        # 3. Определяем режим
        provider = None  # AI создаётся лениво — структурному xls-парсингу он не нужен

        async def _ai_provider():
            nonlocal provider
            if provider is None:
                provider = await create_ai_provider()
            return provider

        is_manager = current_user.role in ("admin", "manager")
        distribute_all = is_manager and detect_distribute_all(query)
        target_teacher_fio = extract_target_teacher(query) if query else ""

        # ── РЕЖИМ 3: Распределить всем преподавателям ─────
        if distribute_all:
            if xls_items is not None:
                items = xls_items
            else:
                prov = await _ai_provider()
                parsed = await prov.parse_schedule_all(extracted_text, user_query=query)
                items = parsed.get("items", [])

            # Группируем по teacher
            by_teacher: dict[str, list[dict]] = {}
            for item in items:
                tname = clean_teacher_name(item.get("teacher", ""))
                if not tname:
                    continue
                key = tname.lower()
                by_teacher.setdefault(key, []).append(item)

            tracker = DuplicateTracker()

            teachers_found = 0
            total_added = 0
            total_skipped = 0
            bad_time = 0
            not_found_names: list[str] = []
            dup_names: list[str] = []
            per_teacher: list[str] = []

            for tname, t_items in by_teacher.items():
                # Есть ли у преподавателя учётная запись в системе?
                user = await find_user_by_teacher_name(db, tname)
                if not user:
                    not_found_names.append(tname)
                    continue

                teachers_found += 1
                await tracker.prime(db, user.id)

                added_here = 0
                skipped_here = 0

                for item in t_items:
                    # Уже есть в календаре (или повтор внутри этого файла)?
                    if tracker.is_duplicate(user.id, item):
                        skipped_here += 1
                        continue

                    # Время от AI может быть кривым — не роняем всю раздачу
                    try:
                        start = _parse_time(item.get("start_time", "09:00"))
                        end = _parse_time(item.get("end_time", "10:30"))
                    except Exception:
                        bad_time += 1
                        continue

                    # День недели тоже может прийти мусором
                    try:
                        dow = int(item.get("day_of_week", 0))
                        if not 0 <= dow <= 6:
                            raise ValueError
                    except (TypeError, ValueError):
                        bad_time += 1
                        continue

                    if not (item.get("title") or "").strip():
                        bad_time += 1
                        continue

                    db.add(Schedule(
                        user_id=user.id,
                        title=item.get("title", ""),
                        day_of_week=dow,
                        start_time=start,
                        end_time=end,
                        group_name=item.get("group_name", ""),
                        room=item.get("room", ""),
                        type=ScheduleType.LESSON,
                        source=ScheduleSource.PDF_IMPORT,
                        created_by=current_user.id,
                    ))
                    added_here += 1

                total_added += added_here
                total_skipped += skipped_here
                per_teacher.append(f"• {user.full_name} — добавлено {added_here}, пропущено дублей {skipped_here}")
                if skipped_here:
                    dup_names.append(clean_teacher_name(tname))

            await db.commit()

            report = f"Распределено {total_added} записей между {teachers_found} преподавателями."
            if per_teacher:
                report += "\n\n" + "\n".join(per_teacher)
            if total_skipped:
                report += f"\n\n️ Пропущено дублей: {total_skipped} — такие пары уже есть в календаре."
            if not_found_names:
                report += f"\n\n⚠️ Нет учётной записи ({len(not_found_names)}): {', '.join(not_found_names)}."
                report += "\nЭти преподаватели не зарегистрированы или их ФИО не совпадает — пары им не добавлены."

            db.add(ChatHistory(
                user_id=current_user.id, role="assistant", content=report,
                context_type="schedule",
            ))
            await db.commit()

            return {
                "status": "distributed",
                "filename": file.filename,
                "items": [],
                "message": report,
                "teachers_found": teachers_found,
                "total_added": total_added,
                "total_skipped": total_skipped,
                "not_found": not_found_names,
                "duplicates": dup_names,
            }

        # ── РЕЖИМ 1/2: Пары конкретного преподавателя ─────
        if target_teacher_fio:
            # Пользователь явно указал ФИО преподавателя
            filter_name = target_teacher_fio
            db.add(ChatHistory(
                user_id=current_user.id, role="assistant",
                content=f"Ищу и добавляю пары преподавателя **{filter_name}**...",
                context_type="schedule",
            ))
            await db.commit()
        else:
            # По умолчанию — свой преподаватель
            filter_name = current_user.full_name or current_user.username

        if xls_items is not None:
            # Структурный разбор: берём занятия нужного преподавателя из items
            items = [it for it in xls_items if names_match(it.get("teacher", ""), filter_name)]
        else:
            prov = await _ai_provider()
            parsed = await prov.parse_schedule(extracted_text, teacher_filter=filter_name, user_query=query)
            items = parsed.get("items", [])

        ai_response = f"Я проанализировал файл **{file.filename}**.\n\n"
        if target_teacher_fio:
            ai_response += f"По запросу — найдено {len(items)} записей для преподавателя **{filter_name}**."
        else:
            ai_response += f"Найдено {len(items)} записей для **{filter_name}**."

        if len(items) == 0:
            ai_response += "\n\nПроверьте, есть ли в файле пары для нужного преподавателя."

        # Формируем items для фронтенда, отсекая дубли с уже существующими парами
        tracker = DuplicateTracker()
        await tracker.prime(db, current_user.id)

        result_items = []
        for item in items:
            candidate = {
                "title": item.get("title", "Без названия"),
                "day_of_week": item.get("day_of_week", 0),
                "start_time": item.get("start_time", "09:00"),
                "end_time": item.get("end_time", "10:30"),
                "group_name": item.get("group_name", ""),
                "room": item.get("room", ""),
                "type": item.get("type", "lesson"),
                "source": "pdf_import",
            }
            if tracker.is_duplicate(current_user.id, candidate):
                continue
            result_items.append(candidate)

        skipped = tracker.skipped
        ai_response += f"\n\nГотово к добавлению: {len(result_items)} записей."
        if skipped:
            ai_response += f"\nПропущено дублей: {skipped} — такие пары уже есть в вашем календаре."

        db.add(ChatHistory(
            user_id=current_user.id, role="assistant",
            content=ai_response, context_type="schedule",
        ))
        await db.commit()

        return {
            "status": "parsed",
            "filename": file.filename,
            "items": result_items,
            "teacher": filter_name,
            "skipped_duplicates": skipped,
            "message": (
                f"Найдено {len(result_items)} новых записей для {filter_name}."
                + (f" Пропущено дублей: {skipped}." if skipped else "")
                + " Проверьте и подтвердите добавление."
            ),
        }

    except Exception as e:
        raw = str(e)

        # Понятные сообщения вместо технических ошибок провайдера
        if "429" in raw or "Rate limit" in raw or "rate limit" in raw:
            friendly = (
                "Превышен лимит запросов к AI-провайдеру. "
                "Бесплатный дневной лимит модели исчерпан — попробуйте позже "
                "или добавьте кредиты/выберите другую модель в настройках AI."
            )
        elif "401" in raw or "invalid_api_key" in raw.lower():
            friendly = "AI-провайдер отклонил API-ключ. Проверьте ключ в настройках AI."
        elif "Не удалось извлечь текст" in raw:
            friendly = raw
        else:
            friendly = f"Ошибка обработки файла: {raw[:400]}"

        db.add(ChatHistory(
            user_id=current_user.id, role="assistant",
            content=friendly,
        ))
        await db.commit()
        # Отдаём 502, чтобы фронтенд показал текст ошибки пользователю
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=friendly)


@router.post("/execute-actions")
async def chat_execute_actions(
    request: Request,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_teacher_or_above),
):
    """Выполняет подтверждённые пользователем действия из чата.

    Тело: {"actions": [{"action": "...", "params": {...}}, ...]}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный JSON")

    actions = body.get("actions") or []
    if not isinstance(actions, list) or not actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Список действий пуст")

    results = await execute_actions(current_user, actions)

    # Пишем отчёт в историю чата
    ok_all = all(r["ok"] for r in results)
    lines = []
    for r in results:
        icon = "✅" if r["ok"] else "❌"
        lines.append(f"{icon} {r['message']}")
    report = "\n".join(lines)

    db.add(ChatHistory(
        user_id=current_user.id,
        role="assistant",
        content=report,
        context_type="action",
    ))
    await db.commit()

    return {"results": results, "ok": ok_all, "report": report}


@router.get("/history", response_model=list[ChatMessageOut])
async def get_chat_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == current_user.id)
        .order_by(ChatHistory.created_at.desc()).limit(limit)
    )
    return [ChatMessageOut.model_validate(m) for m in reversed(result.scalars().all())]