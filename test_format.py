import sys, io, os, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from google import genai

GEMINI_API_KEY = "AIzaSyAZUws0ys316MwsW8DQicBtfdM56JIK2gE"
GEMINI_MODEL = "gemini-2.5-flash"
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "tiktok_downloads")

# Загружаем все _analysis.json
analyses = []
for f in sorted(os.listdir(DOWNLOAD_DIR)):
    if f.endswith("_analysis.json"):
        with open(os.path.join(DOWNLOAD_DIR, f), encoding="utf-8") as fh:
            analyses.append(json.load(fh))

print(f"Найдено анализов: {len(analyses)}")
for a in analyses:
    print(f"  - {a.get('format', {}).get('name', '?')} | {a.get('niche', '?')}")

FORMAT_COMPARE_PROMPT = """Ты эксперт по вирусному контенту в TikTok.

Тебе дан массив JSON-описаний видео одного автора. Каждый JSON описывает структуру и механику отдельного видео.

Твоя задача: определить, есть ли между этими видео общий повторяющийся формат — то есть шаблон, который автор использует намеренно и который, судя по просмотрам, оказался вирусным.

ПРАВИЛА:
— Если общего формата нет или видео слишком разные — верни строго: 0
— Если формат обнаружен — верни ТОЛЬКО валидный JSON без markdown следующей структуры:

{
  "format_name": "короткое название формата (2-5 слов)",
  "confidence": "высокая / средняя / низкая",
  "description": "1-2 предложения: суть формата простыми словами",
  "why_viral": "что именно делает этот формат вирусным — конкретно и честно",
  "reproduction_guide": {
    "concept": "основная идея, которую нужно взять за основу",
    "hook": "как начать видео — что делать в первые 2-3 секунды",
    "structure": [
      {
        "step": 1,
        "name": "название шага",
        "duration": "примерная длительность",
        "what_to_do": "конкретное действие или приём",
        "why": "зачем это нужно для удержания зрителя"
      }
    ],
    "required_elements": ["обязательный элемент 1", "обязательный элемент 2"],
    "avoid": ["чего избегать чтобы не сломать формат"],
    "best_for": "кому и в какой нише лучше всего подойдёт этот формат"
  },
  "evidence": ["ключевой признак из видео 1", "из видео 2"]
}"""

combined = json.dumps(analyses, ensure_ascii=False, indent=2)
full_prompt = FORMAT_COMPARE_PROMPT + "\n\nВот массив анализов видео:\n" + combined

client = genai.Client(api_key=GEMINI_API_KEY)
print("\nОтправляю в Gemini...")
response = client.models.generate_content(model=GEMINI_MODEL, contents=full_prompt)

raw = response.text.strip()
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
    raw = raw.strip()

print("\nОТВЕТ GEMINI:")
print(raw)

# Сохраняем
out = os.path.join(DOWNLOAD_DIR, "viral_format_test.json")
try:
    data = json.loads(raw)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nСохранено: {out}")
except json.JSONDecodeError:
    print("Ответ не JSON (вероятно 0 — формат не найден)")
