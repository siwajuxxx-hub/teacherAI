"""Проверка чанкования: ни один преподаватель не теряется."""
import glob, os, asyncio, re
from app.services.file_parser import extract_text_from_file
from app.services.ai_service import split_schedule_text

DOCX = glob.glob(r"C:\Users\siwaj\.dsh\attachments\v1\files\**\*.docx", recursive=True)
if not DOCX:
    print("DOCX не найден"); raise SystemExit

with open(DOCX[0], "rb") as f:
    text = asyncio.run(extract_text_from_file(f.read(), os.path.basename(DOCX[0])))

print(f"=== Исходный текст: {len(text)} символов ===")

# Было: обрезка до 15000
old = text[:15000]
names_all = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", text))
names_old = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", old))
print(f"  Преподавателей в полном тексте: {len(names_all)}")
print(f"  Было видно AI (обрезка 15000): {len(names_old)}")
print(f"  Терялось: {len(names_all - names_old)}")
for n in sorted(names_all - names_old):
    print(f"    ❌ {n[0]} {n[1]}")

# Стало: чанкование
chunks = split_schedule_text(text)
joined = "".join(chunks)
print(f"\n=== Чанкование ===")
print(f"  Кусков: {len(chunks)}")
for i, c in enumerate(chunks):
    cn = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", c))
    print(f"    кусок {i+1}: {len(c)} символов, {len(cn)} ФИО")

names_chunked = set(re.findall(r"([А-ЯЁ][а-яё]+)\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", joined))
print(f"\n  ФИО доступно AI со всех кусков: {len(names_chunked)} (из {len(names_all)})")
print(f"  Теряется: {len(names_all - names_chunked)}")
assert not (names_all - names_chunked), f"теряются: {names_all - names_chunked}"
assert len(joined) == len(text), "текст повреждён при чанковании"
print("\n  ✅ Чанкование сохраняет ВСЕХ преподавателей и весь текст")

# Куски не рвут записи посередине
print("\n=== Целостность границ ===")
for i, c in enumerate(chunks[:-1]):
    print(f"  кусок {i+1} заканчивается: …{c[-60:].strip()!r}")
    print(f"  кусок {i+2} начинается:   {chunks[i+1][:60].strip()!r}")