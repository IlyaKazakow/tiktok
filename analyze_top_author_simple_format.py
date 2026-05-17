"""
Analyze top viral TikTok creator for AI-reproducible formats.
1. Search for 1M+ view videos
2. Find most popular author
3. Download their top 15 videos
4. Analyze each video for format
5. Filter for simple/AI-reproducible content
6. Detect common viral pattern
"""

import os
import json
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tiktok_search import (
    search_viral_videos, find_top_author, get_author_top_videos,
    filter_simple_formats, download_video, analyze_video, save_analysis,
    find_viral_format, save_format_result, print_video, format_number, DOWNLOAD_DIR
)

def main():
    query = input("Введите поисковый запрос: ").strip()
    if not query:
        print("Запрос не может быть пустым.")
        return

    print("\n" + "="*70)
    print("ПОИСК ВИРУСНОГО ФОРМАТА У ТОП-АВТОРА (1M+ ПРОСМОТРОВ)")
    print("="*70)

    # ШАГ 1: Поиск видео с 1M+ просмотров
    print(f"\n[ШАГ 1] Ищу видео с 1M+ просмотров...")
    try:
        top_videos = search_viral_videos(query, min_views=1_000_000, max_results=20)
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return

    print(f"Найдено: {len(top_videos)} видео")

    if len(top_videos) < 1:
        print("Нет видео с 1M+ просмотров. Попробуйте другой запрос.")
        return

    # ШАГ 2: Найти топ автора
    print("\n[ШАГ 2] Определяю самого популярного автора...")
    try:
        top_author = find_top_author(top_videos)
    except Exception as e:
        print(f"Ошибка: {e}")
        return

    if not top_author:
        print("Не удалось найти топ-автора.")
        return

    # ШАГ 3: Получить топ 15 видео автора
    print(f"\n[ШАГ 3] Получаю топ 15 видео автора @{top_author}...")
    try:
        author_videos = get_author_top_videos(top_author, limit=15)
    except Exception as e:
        print(f"Ошибка при получении видео: {e}")
        return

    print(f"Получено: {len(author_videos)} видео\n")

    for i, v in enumerate(author_videos, 1):
        views = v.get("views") or 0
        title = (v.get("title") or "")[:50]
        print(f"  [{i:2d}] {format_number(views):>6} | {title}")

    # ШАГ 4: Подтверждение
    confirm = input(f"\nСкачать, анализировать и найти формат? (y/n): ").strip().lower()
    if confirm != "y":
        print("Отменено.")
        return

    # ШАГ 5: Скачивание и анализ
    print(f"\n[ШАГ 4] Скачиваю видео...")
    download_dir_subdir = os.path.join(DOWNLOAD_DIR, f"top_author_{top_author}")
    os.makedirs(download_dir_subdir, exist_ok=True)

    downloaded = []
    for i, v in enumerate(author_videos, 1):
        video_url = v.get("video", {}).get("url")
        if not video_url:
            print(f"  [{i:2d}] Нет ссылки, пропускаю")
            continue

        try:
            video_id = v.get("id", "unknown")
            filename = f"{i:02d}_{top_author}_{video_id}.mp4"
            filepath = os.path.join(download_dir_subdir, filename)

            if not os.path.exists(filepath):
                print(f"  [{i:2d}] Скачиваю {filename}...")
                import requests
                r = requests.get(video_url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()

                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

                size_mb = os.path.getsize(filepath) / 1_048_576
                print(f"      OK ({size_mb:.1f} МБ)")
            else:
                print(f"  [{i:2d}] Уже существует")

            downloaded.append((filepath, v))
        except Exception as e:
            print(f"  [{i:2d}] Ошибка: {e}")

    print(f"\nСкачано: {len(downloaded)}/{len(author_videos)}")

    # ШАГ 6: Анализ каждого видео
    print(f"\n[ШАГ 5] Анализирую видео через Gemini...")
    analyses = []
    for i, (filepath, v) in enumerate(downloaded, 1):
        print(f"  [{i}/{len(downloaded)}] {os.path.basename(filepath)}")
        try:
            data = analyze_video(filepath)
            save_analysis(filepath, data)
            analyses.append(data)

            fmt = data.get("format", {})
            print(f"      Формат: {fmt.get('name', '?')}")
            print(f"      Техника: {fmt.get('structure', [{}])[0].get('technique', '?')}")
        except Exception as e:
            print(f"      Ошибка: {e}")

    if len(analyses) < 2:
        print(f"\nНедостаточно видео для анализа ({len(analyses)}). Нужно минимум 2.")
        return

    # ШАГ 7: Фильтр по простоте
    print(f"\n[ШАГ 6] Фильтрую контент по простоте (AI-воспроизводимость)...")
    simple_analyses = filter_simple_formats(analyses)
    print(f"Простых форматов: {len(simple_analyses)}/{len(analyses)}")

    if len(simple_analyses) < 2:
        print("Недостаточно простых форматов для сравнения.")
        print("Используя все видео вместо фильтрованных...")
        final_analyses = analyses
    else:
        final_analyses = simple_analyses

    # ШАГ 8: Поиск вирусного формата
    print(f"\n[ШАГ 7] Ищу общий вирусный формат в {len(final_analyses)} видео...")
    try:
        result = find_viral_format(final_analyses)
    except Exception as e:
        print(f"Ошибка: {e}")
        return

    # ШАГ 9: Вывод результатов
    print("\n" + "="*70)
    print("РЕЗУЛЬТАТ АНАЛИЗА")
    print("="*70)

    if result.strip() == "0":
        print("\nОбщего вирусного формата не обнаружено.")
        print("Видео используют разные подходы.")
    else:
        try:
            parsed = json.loads(result)
            fmt_name = parsed.get("format_name", "?")
            confidence = parsed.get("confidence", "?")
            desc = parsed.get("description", "")
            why = parsed.get("why_viral", "")

            print(f"\nФОРМАТ НАЙДЕН!")
            print(f"\n  Название:     {fmt_name}")
            print(f"  Уверенность:  {confidence}")
            print(f"  Описание:     {desc}")
            print(f"  Почему вирусный: {why}")

            guide = parsed.get("reproduction_guide", {})
            print(f"\n  КАК ПОВТОРИТЬ:")
            print(f"    Концепция: {guide.get('concept', '')}")
            print(f"    Хук: {guide.get('hook', '')}")

            print(f"\n    Шаги:")
            for step in guide.get("structure", []):
                print(f"      {step.get('step')}. {step.get('name')} ({step.get('duration')})")
                print(f"         → {step.get('what_to_do')}")

            print(f"\n    Обязательные элементы:")
            for elem in guide.get("required_elements", []):
                print(f"      • {elem}")

            print(f"\n    Избегать:")
            for avoid in guide.get("avoid", []):
                print(f"      • {avoid}")

            print(f"\n    Подходит для: {guide.get('best_for', '')}")

            # Сохраняем
            out_path = os.path.join(download_dir_subdir, f"viral_format_{top_author}_simple.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            print(f"\n  Сохранено: {out_path}")

        except json.JSONDecodeError as e:
            print(f"\nОшибка парсинга JSON: {e}")
            print(f"Ответ: {result}")

    print("\n" + "="*70)
    print(f"Все файлы в: {download_dir_subdir}")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
