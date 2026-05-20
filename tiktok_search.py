"""
TikTok Video Search via apidojo~tiktok-scraper (Apify)
1. Search by keyword, filter 50k+ views, pick 1 random video
2. Scrape that author's profile, get last 40 videos
3. Randomly pick 5, download them
4. Transcribe each video via Google Gemini
"""

import os
import random
import time
import requests
from google import genai
from google.genai import types


def getenv_required(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(f"Environment variable {key} is required.")
    return value

APIFY_TOKEN = getenv_required("APIFY_TOKEN")
ACTOR_ID = os.getenv("ACTOR_ID", "apidojo~tiktok-scraper")
GEMINI_API_KEY = getenv_required("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
RUNWAY_API_KEY = getenv_required("RUNWAY_API_KEY")
RUNWAY_API_BASE = os.getenv("RUNWAY_API_BASE", "https://api.dev.runwayml.com/v1")
MIN_VIEWS = int(os.getenv("MIN_VIEWS", "10000"))
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "tiktok_downloads")


# ─── APIFY ──────────────────────────────────────────────────────────────────

def run_actor(payload: dict) -> list:
    """Start actor run, poll until finished, return dataset items."""
    # 1. Запускаем актор асинхронно
    run_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}&memory=512"
    r = requests.post(run_url, json=payload, timeout=30)
    r.raise_for_status()
    run_data = r.json()
    run_id = run_data["data"]["id"]
    print(f"  Актор запущен (run: {run_id}), жду завершения...")

    # 2. Опрашиваем статус раз в 5 секунд
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
    for _ in range(60):  # макс 5 мин
        time.sleep(5)
        s = requests.get(status_url, timeout=15).json()
        status = s["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Актор завершился со статусом: {status}")

    # 3. Забираем результаты из датасета
    dataset_id = s["data"]["defaultDatasetId"]
    items_url = (
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?token={APIFY_TOKEN}&format=json&clean=true"
    )
    items = requests.get(items_url, timeout=30).json()
    return items


def search_videos(query: str, max_items: int = 50) -> list:
    print(f'Ищу по запросу "{query}" (ожидание 30-60 сек)...')
    raw = run_actor({
        "keywords": [query],
        "maxItems": max_items,
        "sortType": "RELEVANCE",
        "dateRange": "DEFAULT",
    })
    # Actor возвращает {"noResults": true}-плейсхолдеры когда ничего не нашёл — отфильтровываем
    return [v for v in raw if not v.get("noResults")]


def get_profile_videos(username: str, max_items: int = 40) -> list:
    print(f"Скрейплю профиль @{username} (ожидание 30-60 сек)...")
    return run_actor({
        "startUrls": [f"https://www.tiktok.com/@{username}"],
        "maxItems": max_items,
    })


# ─── ФИЛЬТР ─────────────────────────────────────────────────────────────────

def _views(v: dict) -> int:
    """Read view count tolerantly — Apify actors use different field names."""
    return (
        v.get("views")
        or v.get("playCount")
        or v.get("viewCount")
        or v.get("play_count")
        or 0
    )


def filter_by_views(videos: list, min_views: int = MIN_VIEWS) -> list:
    return [v for v in videos if _views(v) >= min_views]


def search_viral_videos(query: str, min_views: int = 1_000_000, max_results: int = 20) -> list:
    print(f'Ищу видео с {format_number(min_views)}+ просмотров...')
    raw = search_videos(query, max_items=100)
    filtered = [v for v in raw if _views(v) >= min_views]
    return filtered[:max_results]


def find_top_author(videos: list) -> str:
    author_stats = {}
    for video in videos:
        author = video.get("channel", {}).get("username")
        if not author:
            continue
        if author not in author_stats:
            author_stats[author] = {"total_views": 0, "count": 0}
        author_stats[author]["total_views"] += _views(video)
        author_stats[author]["count"] += 1

    if not author_stats:
        return None

    top_author, stats = max(author_stats.items(), key=lambda x: x[1]["total_views"])
    print(f"\nТоп автор: @{top_author}")
    print(f"  Всего просмотров: {format_number(stats['total_views'])}")
    print(f"  Видео в результатах: {stats['count']}")
    return top_author


def get_author_top_videos(author: str, limit: int = 15) -> list:
    profile_videos = get_profile_videos(author, max_items=40)
    sorted_videos = sorted(profile_videos, key=lambda v: v.get("views", 0), reverse=True)
    return sorted_videos[:limit]


def filter_simple_formats(analyses: list) -> list:
    complexity_markers = [
        "special effects", "advanced editing", "acrobatic",
        "specific personality", "unique location", "rare item",
        "professional skill", "высокая сложность"
    ]

    reproducibility_markers = [
        "text overlay", "reaction", "transition", "lip-sync",
        "setup-punchline", "costume change", "sync with music",
        "simple pose", "mirror effect", "split screen",
        "текстовый оверлей", "реакция", "синхронизация"
    ]

    simple_analyses = []
    for analysis in analyses:
        format_desc = analysis.get("format", {}).get("pattern", "").lower()
        technique = analysis.get("format", {}).get("structure", [{}])[0].get("technique", "").lower()

        has_complexity = any(marker in format_desc or marker in technique for marker in complexity_markers)
        if has_complexity:
            continue

        reproducible_count = sum(
            1 for marker in reproducibility_markers
            if marker in format_desc or marker in technique
        )

        if reproducible_count >= 2:
            simple_analyses.append(analysis)

    return simple_analyses


# ─── СКАЧИВАНИЕ ─────────────────────────────────────────────────────────────

def download_video(video: dict, index: int) -> str | None:
    video_url = video.get("video", {}).get("url")
    if not video_url:
        print(f"  [!] Нет ссылки на видео у #{index}")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    author = video.get("channel", {}).get("username", "unknown")
    video_id = video.get("id", "unknown")
    filename = f"{index:02d}_{author}_{video_id}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    print(f"  Скачиваю [{index}] @{author} → {filename}")
    r = requests.get(video_url, stream=True, timeout=60,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)

    size_mb = os.path.getsize(filepath) / 1_048_576
    print(f"    ✓ Сохранено ({size_mb:.1f} МБ): {filepath}")
    return filepath


# ─── ТРАНСКРИПЦИЯ И АНАЛИЗ GEMINI ───────────────────────────────────────────

SCENE_PROMPT = """Ты аналитик вирусного контента. Твоя задача — описать СТРУКТУРУ и СУТЬ этого видео так, чтобы другая языковая модель могла сравнить его с другими видео и определить, принадлежат ли они к одному формату.

Тебя НЕ интересует конкретный сюжет. Тебя интересует ШАБЛОН: как видео устроено, какой механизм удержания внимания используется, что делает его потенциально вирусным.

Верни ТОЛЬКО валидный JSON без markdown:
{
  "transcript": "дословная речь из видео или 'Речи нет'",

  "format": {
    "name": "короткое название формата (2-5 слов, например: 'дети в роли взрослых', 'реакция на испытание', 'до и после')",
    "pattern": "описание шаблона в 1-2 предложениях — как устроено большинство видео этого типа",
    "structure": [
      {
        "part": "название части (хук / завязка / кульминация / развязка / призыв)",
        "start": "0:00",
        "end": "0:05",
        "role": "какую функцию выполняет эта часть в удержании зрителя",
        "technique": "конкретный приём (неожиданность / милота / конфликт / юмор / трансформация / загадка / и т.д.)"
      }
    ]
  },

  "viral_mechanics": {
    "hook": "как первые 2-3 секунды цепляют внимание",
    "retention": "что заставляет досматривать до конца",
    "shareability": "почему это хочется переслать (или нет)",
    "emotional_trigger": "основная эмоция зрителя (умиление / смех / удивление / узнавание / вдохновение / и т.д.)"
  },

  "creator_role": "участник / рассказчик / наблюдатель / режиссёр",
  "protagonist": "кто главный герой и почему он вызывает интерес",
  "recurring_elements": ["элемент1", "элемент2"],
  "target_audience": "кому это будет близко",
  "niche": "тематическая ниша (семья / юмор / лайфхаки / дети / домашние животные / и т.д.)"
}"""


def _upload_and_wait(client, filepath: str):
    """Upload file to Gemini Files API and wait until ready."""
    video_file = client.files.upload(
        file=filepath,
        config=types.UploadFileConfig(mime_type="video/mp4"),
    )
    while video_file.state.name == "PROCESSING":
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)
    if video_file.state.name == "FAILED":
        raise RuntimeError("Gemini не смог обработать файл")
    return video_file


def analyze_video(filepath: str) -> dict:
    """Transcribe and split video into scenes via Gemini. Returns parsed dict."""
    import json
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"  Загружаю в Gemini: {os.path.basename(filepath)}...")
    video_file = _upload_and_wait(client, filepath)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[types.Content(parts=[
                    types.Part(file_data=types.FileData(
                        file_uri=video_file.uri,
                        mime_type="video/mp4",
                    )),
                    types.Part(text=SCENE_PROMPT),
                ])]
            )
            break
        except Exception as e:
            print(f"  Попытка {attempt + 1}/3: {e}")
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

    return json.loads(raw)


def save_analysis(filepath: str, data: dict) -> str:
    """Save JSON analysis next to the video file."""
    import json
    json_path = os.path.splitext(filepath)[0] + "_analysis.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return json_path


# ─── ПОИСК ВИРУСНОГО ФОРМАТА ─────────────────────────────────────────────────

FORMAT_COMPARE_PROMPT = """Ты эксперт по вирусному контенту в TikTok.

Тебе дан массив JSON-описаний видео одного автора. Каждый JSON описывает структуру и механику отдельного видео.

Твоя задача: определить, есть ли между этими видео общий повторяющийся формат — то есть шаблон, который автор использует намеренно и который, судя по просмотрам, оказался вирусным.

ПРАВИЛА:
— Если общего формата нет или видео слишком разные — верни строго: 0
— Если формат обнаружен — верни ТОЛЬКО валидный JSON без markdown следующей структуры:

{
  "format_name": "короткое название формата (2-5 слов)",
  "confidence": "высокая / средняя / низкая — насколько уверен в совпадении",
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
  "evidence": ["цитата или ключевой признак из видео 1", "из видео 2"]
}"""


def find_viral_format(analyses: list) -> str:
    """Send all video analyses to Gemini and detect common viral format."""
    import json
    client = genai.Client(api_key=GEMINI_API_KEY)

    combined = json.dumps(analyses, ensure_ascii=False, indent=2)
    prompt = f"{FORMAT_COMPARE_PROMPT}\n\nВот массив анализов видео:\n{combined}"

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            break
        except Exception as e:
            print(f"  Попытка {attempt + 1}/3: {e}")
            if attempt < 2:
                time.sleep(15)
            else:
                raise

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def save_format_result(author: str, result: str) -> str:
    import json
    out_path = os.path.join(DOWNLOAD_DIR, f"viral_format_{author}.json")
    try:
        data = json.loads(result)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result)
    return out_path


# ─── УТИЛИТЫ ────────────────────────────────────────────────────────────────

def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def print_video(i: int, v: dict) -> None:
    author = v.get("channel", {}).get("username", "unknown")
    desc = (v.get("title") or "")[:70]
    views = v.get("views") or 0
    link = v.get("postPage", "N/A")
    # Handle emoji and special characters
    desc_safe = desc.encode('ascii', 'ignore').decode('ascii')
    print(f"  [{i:2d}] @{author} | {format_number(views)} просмотров")
    print(f"        {desc_safe}")
    print(f"        {link}")


# ─── ГЕНЕРАЦИЯ ВИДЕО ЧЕРЕЗ RUNWAYML ─────────────────────────────────────────

def select_simplest_format(format_data: dict) -> dict:
    """Select the simplest scenario from reproduction_guide."""
    guide = format_data.get("reproduction_guide", {})
    required = guide.get("required_elements", [])

    # Filter out complex requirements
    complex_keywords = [
        "acrobatic", "special effects", "professional", "advanced",
        "rare", "specific personality", "unique location",
        "высокая сложность", "спецэффекты", "профессиональное"
    ]

    if any(kw.lower() in str(required).lower() for kw in complex_keywords):
        return None

    return format_data if len(required) <= 5 else None


def generate_video_prompt(format_data: dict) -> str:
    """Generate English prompt for Runway from reproduction_guide."""
    guide = format_data.get("reproduction_guide", {})
    concept = guide.get("concept", "")
    hook = guide.get("hook", "")

    steps_desc = []
    for step in guide.get("structure", []):
        what = step.get("what_to_do", "")
        duration = step.get("duration", "")
        steps_desc.append(f"- {what} ({duration})")

    steps_text = "\n".join(steps_desc) if steps_desc else ""

    prompt = f"""Create a viral TikTok video (15-30 seconds, 9:16 format).

Concept: {concept}

Hook (first 2-3 seconds): {hook}

Steps to follow:
{steps_text}

Make it engaging, simple to reproduce, and optimized for viral TikTok sharing.
Use bright colors, clear movement, and immediate visual appeal.
Keep it authentic and easy to follow."""

    return prompt


def generate_viral_video(format_data: dict, author: str) -> dict | None:
    """Generate video via RunwayML API (Gen-4 text-to-video).

    Returns {"path": local_filepath, "url": public_runway_url} on success, None on failure.
    """
    if not select_simplest_format(format_data):
        print("  [!] Формат слишком сложный для генерации")
        return None

    prompt = generate_video_prompt(format_data)
    fmt_name = format_data.get("format_name", "unknown")

    print(f"  Генерирую видео для формата: {fmt_name}")
    print(f"  Промпт: {prompt[:120]}...")

    headers = {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
        "X-Runway-Version": "2024-11-06",
        "Content-Type": "application/json",
    }

    payload = {
        "promptText": prompt,
        "model": "gen4_turbo",
        "ratio": "768:1280",
        "duration": 10,
    }

    try:
        response = requests.post(
            f"{RUNWAY_API_BASE}/text_to_video",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data.get("id")

        if not task_id:
            print(f"  [!] Не получен task_id: {task_data}")
            return None

        print(f"  Задача запущена (task_id: {task_id}), жду генерации...")

        for attempt in range(60):  # до 10 минут
            time.sleep(10)
            status_response = requests.get(
                f"{RUNWAY_API_BASE}/tasks/{task_id}",
                headers=headers,
                timeout=15,
            )
            status_response.raise_for_status()
            status_data = status_response.json()
            status = status_data.get("status")

            if status == "SUCCEEDED":
                output = status_data.get("output", [])
                video_url = output[0] if output else None
                if video_url:
                    print(f"  Видео готово, скачиваю...")
                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in fmt_name)
                    filename = f"generated_viral_{safe_name}_{int(time.time())}.mp4"
                    filepath = os.path.join(DOWNLOAD_DIR, filename)

                    video_response = requests.get(video_url, timeout=120)
                    video_response.raise_for_status()
                    with open(filepath, "wb") as f:
                        f.write(video_response.content)

                    size_mb = os.path.getsize(filepath) / 1_048_576
                    print(f"  Сохранено ({size_mb:.1f} МБ): {filepath}")
                    return {"path": filepath, "url": video_url}
                else:
                    print(f"  [!] Нет URL в ответе: {status_data}")
                    return None

            elif status in ("FAILED", "CANCELED"):
                print(f"  [!] Генерация не удалась: {status}")
                print(f"      {status_data.get('failure', '')}")
                return None

            else:
                print(f"  Статус: {status} ({attempt + 1}/60)...")

        print(f"  [!] Timeout при ожидании генерации")
        return None

    except requests.exceptions.RequestException as e:
        print(f"  [!] Ошибка при запросе к RunwayML: {e}")
        return None


# ─── ВЕБ-ФЛОУ (НЕИНТЕРАКТИВНЫЙ) ─────────────────────────────────────────────

def run_pipeline(query: str, progress=None, skip_generation: bool = False) -> dict:
    """Non-interactive full pipeline for web use.

    If skip_generation=True, returns after Gemini format analysis
    (no RunwayML call — saves money during testing).

    Calls progress(step, total, message) at each milestone.
    Returns dict with: success, error, author, top_videos, format_info,
    video_url, video_path.
    """
    import json

    total_steps = 7 if skip_generation else 8
    result = {
        "success": False,
        "error": None,
        "author": None,
        "top_videos": [],
        "format_info": None,
        "video_url": None,
        "video_path": None,
    }

    def emit(step, msg):
        if progress:
            progress(step, total_steps, msg)

    # Шаг 1: поиск (1 Apify-запрос) + каскадный фильтр по просмотрам
    emit(1, "Ищу видео по запросу...")
    raw_videos = search_videos(query, max_items=100)

    # Диагностика в Railway логи — пригодится если что-то идёт не так
    if raw_videos:
        sample_keys = list(raw_videos[0].keys())[:15]
        print(f"DEBUG: Apify вернул {len(raw_videos)} видео. Поля первого: {sample_keys}", flush=True)
        sample_views = [_views(v) for v in raw_videos[:5]]
        print(f"DEBUG: Просмотры первых 5 видео: {sample_views}", flush=True)

    filtered = []
    used_threshold = None
    for threshold in (1_000_000, 500_000, 100_000, 10_000):
        candidates = [v for v in raw_videos if _views(v) >= threshold]
        if candidates:
            filtered = candidates[:20]
            used_threshold = threshold
            break

    if not filtered:
        max_v = max((_views(v) for v in raw_videos), default=0)
        sample_keys = list(raw_videos[0].keys())[:12] if raw_videos else []
        result["error"] = (
            f"Apify вернул {len(raw_videos)} видео, но макс. просмотров: {max_v:,}. "
            f"Поля в данных: {sample_keys}. "
            f"Скорее всего, новый Apify токен с ограничениями (free trial). "
            f"Проверь квоту в console.apify.com → Billing."
        )
        return result

    # Шаг 2: топ-автор по сумме просмотров
    if used_threshold >= 1_000_000:
        threshold_label = "1M"
    elif used_threshold >= 1000:
        threshold_label = f"{used_threshold // 1000}K"
    else:
        threshold_label = str(used_threshold)
    emit(2, f"Найдено {len(filtered)} видео с {threshold_label}+ просмотров. Определяю топ-автора...")
    author = find_top_author(filtered)
    if not author:
        result["error"] = "Не удалось определить автора"
        return result
    result["author"] = author

    # Шаг 3: профиль автора
    emit(3, f"Скрейплю профиль @{author}...")
    profile_videos = get_profile_videos(author, max_items=40)
    if not profile_videos:
        result["error"] = f"Профиль @{author} пуст или не найден"
        return result

    # Шаг 4: топ-5 по просмотрам
    top_5 = sorted(profile_videos, key=lambda v: v.get("views", 0), reverse=True)[:5]
    result["top_videos"] = [
        {
            "views": v.get("views", 0),
            "title": (v.get("title") or "")[:120],
            "url": v.get("postPage"),
        }
        for v in top_5
    ]
    emit(4, f"Выбрал топ-{len(top_5)} видео автора по просмотрам")

    # Шаг 5: скачивание
    downloaded = []
    download_errors = []
    for i, v in enumerate(top_5, 1):
        emit(5, f"Скачиваю видео {i}/{len(top_5)}...")
        try:
            path = download_video(v, i)
            if path:
                downloaded.append(path)
        except requests.exceptions.RequestException as e:
            download_errors.append(f"Видео {i}: {type(e).__name__}: {e}")

    if len(downloaded) < 2:
        details = " | ".join(download_errors) if download_errors else "нет деталей"
        result["error"] = f"Скачано только {len(downloaded)} видео — недостаточно для анализа. {details}"
        return result

    # Шаг 6: Gemini анализ
    analyses = []
    analysis_errors = []
    for i, filepath in enumerate(downloaded, 1):
        emit(6, f"Анализирую видео {i}/{len(downloaded)} через Gemini...")
        try:
            data = analyze_video(filepath)
            analyses.append(data)
        except Exception as e:
            err_short = f"{type(e).__name__}: {str(e)[:160]}"
            analysis_errors.append(f"Видео {i}: {err_short}")
            emit(6, f"Видео {i}: ОШИБКА — {err_short[:120]}")

    if len(analyses) < 2:
        details = " | ".join(analysis_errors) if analysis_errors else "нет деталей"
        result["error"] = f"Успешно проанализировано только {len(analyses)} — нужно минимум 2. Причины: {details}"
        return result

    # Шаг 7: поиск формата
    emit(7, f"Ищу общий вирусный формат по {len(analyses)} видео...")
    format_raw = find_viral_format(analyses)

    if format_raw.strip() == "0":
        result["error"] = "Общего вирусного формата у автора не найдено"
        return result

    try:
        format_data = json.loads(format_raw)
        result["format_info"] = format_data
    except json.JSONDecodeError:
        result["error"] = "Не удалось распарсить результат анализа формата"
        return result

    # Если режим "только анализ" — выходим тут (без RunwayML)
    if skip_generation:
        result["success"] = True
        return result

    # Шаг 7.5: проверка простоты формата
    if not select_simplest_format(format_data):
        result["error"] = "Формат слишком сложный для автогенерации. Но анализ доступен."
        result["success"] = True  # partial — есть анализ, но без видео
        return result

    # Шаг 8: генерация через RunwayML
    emit(8, "Генерирую видео через RunwayML (~5-10 мин)...")
    generated = generate_viral_video(format_data, author)
    if not generated:
        result["error"] = "Генерация видео не удалась (проверь RUNWAY_API_KEY и логи)"
        result["success"] = True  # partial — есть анализ
        return result

    result["video_url"] = generated["url"]
    result["video_path"] = generated["path"]
    result["success"] = True
    return result


# ─── ГЛАВНЫЙ ФЛОУ ───────────────────────────────────────────────────────────

def main():
    query = input("Введите поисковый запрос: ").strip()
    if not query:
        print("Запрос не может быть пустым.")
        return

    # Шаг 1: поиск вирусных видео (1M+ просмотров)
    try:
        filtered = search_viral_videos(query, min_views=1_000_000, max_results=20)
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при поиске: {e}")
        return

    print(f"Найдено {len(filtered)} видео с 1M+ просмотров.\n")

    if not filtered:
        print("Попробуйте другой запрос.")
        return

    # Шаг 2: случайное видео из результатов
    chosen = random.choice(filtered)
    author = chosen.get("channel", {}).get("username", "unknown")
    print("Случайно выбрано видео:")
    print_video(1, chosen)
    print(f"\nАвтор: @{author}\n")

    # Шаг 3: профиль автора
    try:
        profile_videos = get_profile_videos(author, max_items=40)
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при скрейпинге профиля: {e}")
        return

    if not profile_videos:
        print("Профиль пуст или не найден.")
        return

    print(f"\nПоследние {len(profile_videos)} видео @{author}:\n")
    for i, v in enumerate(profile_videos, 1):
        print_video(i, v)

    # Шаг 4: топ-5 по просмотрам
    pick_count = min(5, len(profile_videos))
    to_download = sorted(profile_videos, key=lambda v: v.get("views", 0), reverse=True)[:pick_count]

    print(f"\nТоп-{pick_count} видео автора по просмотрам:\n")
    for i, v in enumerate(to_download, 1):
        print_video(i, v)

    confirm = input(f"\nСкачать и транскрибировать {pick_count} видео? (y/n): ").strip().lower()
    if confirm != "y":
        print("Отменено.")
        return

    # Шаг 5: скачивание + транскрипция
    print(f"\nСкачиваю в: {DOWNLOAD_DIR}\n")
    downloaded = []
    for i, v in enumerate(to_download, 1):
        try:
            path = download_video(v, i)
            if path:
                downloaded.append(path)
        except requests.exceptions.RequestException as e:
            print(f"  [!] Ошибка скачивания [{i}]: {e}")

    print(f"\nСкачано {len(downloaded)}/{pick_count}. Начинаю анализ...\n")

    analyses = []
    for i, filepath in enumerate(downloaded, 1):
        print(f"[{i}/{len(downloaded)}] Анализирую: {os.path.basename(filepath)}")
        try:
            data = analyze_video(filepath)
            save_analysis(filepath, data)
            analyses.append(data)

            fmt = data.get("format", {})
            print(f"  Формат: {fmt.get('name', '?')}")
            print(f"  Транскрипт: {data.get('transcript', '')[:100]}...")
            print(f"  Ниша: {data.get('niche', '?')}\n")
        except Exception as e:
            print(f"  [!] Ошибка анализа: {e}\n")

    # Шаг 6: поиск общего вирусного формата
    if len(analyses) < 2:
        print("Недостаточно видео для сравнения форматов.")
        return

    print(f"\n{'─'*60}")
    print(f"Шаг 6: ищу общий вирусный формат по {len(analyses)} видео...")
    print(f"{'─'*60}\n")

    try:
        result = find_viral_format(analyses)

        if result.strip() == "0":
            print("Общего вирусного формата не обнаружено.")
            print(f"Индивидуальные анализы сохранены в: {DOWNLOAD_DIR}")
        else:
            import json
            try:
                parsed = json.loads(result)
                fmt_name = parsed.get("format_name", "?")
                confidence = parsed.get("confidence", "?")
                description = parsed.get("description", "")
                why_viral = parsed.get("why_viral", "")

                print(f"ВИРУСНЫЙ ФОРМАТ НАЙДЕН!")
                print(f"  Название:    {fmt_name}")
                print(f"  Уверенность: {confidence}")
                print(f"  Суть:        {description}")
                print(f"  Почему вирусный: {why_viral}")

                guide = parsed.get("reproduction_guide", {})
                print(f"\n  Как воспроизвести:")
                print(f"    Концепция: {guide.get('concept', '')}")
                print(f"    Хук: {guide.get('hook', '')}")
                for step in guide.get("structure", []):
                    print(f"    Шаг {step.get('step')}: {step.get('what_to_do', '')}")

            except json.JSONDecodeError:
                print(result)

            out_path = save_format_result(author, result)
            print(f"\n  Полный результат сохранён: {out_path}")

            # Шаг 7: генерация видео на основе найденного формата
            print(f"\n{'─'*60}")
            print(f"Шаг 7: генерирую видео на основе вирусного формата...")
            print(f"{'─'*60}\n")

            try:
                format_json = json.loads(result)
                generated = generate_viral_video(format_json, author)
                if generated:
                    print(f"\n✓ Видео успешно сгенерировано: {generated['path']}")
                    print(f"  URL: {generated['url']}")
                else:
                    print(f"\n[!] Генерация видео не удалась или ключ не установлен")
            except (json.JSONDecodeError, Exception) as e:
                print(f"[!] Ошибка при генерации видео: {e}")

    except Exception as e:
        print(f"[!] Ошибка при поиске формата: {e}")

    print(f"\nВсе файлы в: {DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()
