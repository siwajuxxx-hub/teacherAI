"""Диагностика: сколько текста в DOCX и какие преподаватели там есть."""
import asyncio, re, sys
from app.services.file_parser import extract_text_from_file

DOCX = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovoch).docx"

import glob, os
files = glob.glob(r"C:\Users\siwaj\.dsh\attachments\v1\files\**\*.docx", recursive=True)
print("Найденные DOCX:")
for f in files:
    print(f"  {os.path.getsize(f):>9} байт  {os.path.basename(f)[:90]}")

target = files[0] if files else None
if target:
    with open(target, "rb") as fh:
        data = fh.read()
    text = asyncio.run(extract_text_from_file(data, os.path.basename(target)))
    print(f"\n=== {os.path.basename(target)} ===")
    print(f"  Длина текста: {len(text)} символов")
    print(f"  Обрезается до 15000? {'ДА — теряется ' + str(len(text) - 15000) + ' символов' if len(text) > 15000 else 'нет'}")

    # Ищем ФИО-подобные конструкции
    names = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", text))
    print(f"\n  Найдено ФИО-паттернов: {len(names)}")
    for n in sorted(names)[:40]:
        print(f"    {n[0]} {n[1]}")

    # Проверяем ключевые фамилии
    print("\n  Ключевые фамилии в тексте:")
    for surname in ["Шапуленкова", "Болохов", "Гаврилов", "Певцова", "Черненкова"]:
        pos = text.find(surname)
        print(f"    {surname:15} {'на позиции ' + str(pos) if pos >= 0 else 'НЕ НАЙДЕНО'}"
              f"{'  (за пределами 15000!)' if pos >= 15000 else ''}")

    # Что попадает в первые 15000
    head = text[:15000]
    head_names = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", head))
    print(f"\n  В первых 15000 символов ФИО: {len(head_names)}")
    print(f"  В остатке: {len(names - head_names)} — они ТЕРЯЮТСЯ")