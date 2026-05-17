import sys, io, os, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from google import genai
from google.genai import types

GEMINI_API_KEY = "AIzaSyAZUws0ys316MwsW8DQicBtfdM56JIK2gE"
GEMINI_MODEL = "gemini-2.5-flash"
SCENE_PROMPT = """Ты аналитик вирусного контента. Твоя задача - описать СТРУКТУРУ и СУТЬ этого видео так, чтобы другая языковая модель могла сравнить его с другими видео и определить, принадлежат ли они к одному формату.

Тебя НЕ интересует конкретный сюжет. Тебя интересует ШАБЛОН: как видео устроено, какой механизм удержания внимания используется, что делает его потенциально вирусным.

Верни ТОЛЬКО валидный JSON без markdown:
{
  "transcript": "дословная речь из видео или Речи нет",
  "format": {
    "name": "короткое название формата (2-5 слов)",
    "pattern": "описание шаблона в 1-2 предложениях",
    "structure": [
      {
        "part": "хук / завязка / кульминация / развязка",
        "start": "0:00",
        "end": "0:05",
        "role": "какую функцию выполняет эта часть",
        "technique": "конкретный приём (неожиданность / милота / юмор / и т.д.)"
      }
    ]
  },
  "viral_mechanics": {
    "hook": "как первые 2-3 секунды цепляют внимание",
    "retention": "что заставляет досматривать до конца",
    "shareability": "почему хочется переслать",
    "emotional_trigger": "основная эмоция зрителя"
  },
  "creator_role": "участник / рассказчик / наблюдатель / режиссёр",
  "protagonist": "кто главный герой и почему вызывает интерес",
  "recurring_elements": ["элемент1", "элемент2"],
  "target_audience": "кому это будет близко",
  "niche": "тематическая ниша"
}"""

filepath = r"C:\Users\i.kazakov\tiktok_downloads\test_elvitok2020_7066905883782991106.mp4"
print(f"Файл: {os.path.basename(filepath)} ({os.path.getsize(filepath)/1048576:.1f} MB)")

client = genai.Client(api_key=GEMINI_API_KEY)

print("Загружаю в Gemini...")
with open(filepath, "rb") as f:
    video_file = client.files.upload(file=f, config=types.UploadFileConfig(mime_type="video/mp4"))

while video_file.state.name == "PROCESSING":
    time.sleep(3)
    video_file = client.files.get(name=video_file.name)

print(f"Статус: {video_file.state.name}")

for attempt in range(3):
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(parts=[
                types.Part(file_data=types.FileData(file_uri=video_file.uri, mime_type="video/mp4")),
                types.Part(text=SCENE_PROMPT),
            ])]
        )
        break
    except Exception as e:
        print(f"Попытка {attempt+1} неудачна: {e}")
        if attempt < 2:
            time.sleep(15)
        else:
            raise
client.files.delete(name=video_file.name)

raw = response.text.strip()
if raw.startswith("```"):
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
    raw = raw.strip()

data = json.loads(raw)
print("Транскрипт:", data.get("transcript", "")[:300])
print(f"Сцен: {len(data.get('scenes', []))}")
for s in data.get("scenes", []):
    print(f"  [{s['start']} - {s['end']}] {s['description'][:60]}")
print("\nПолный JSON:")
print(json.dumps(data, ensure_ascii=False, indent=2))
print("\nOK")
