# Стабилизация взгляда в VR — сайт с результатами

[![Build and deploy docs](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml/badge.svg)](https://github.com/777werona-afk/vr-gaze-site/actions/workflows/deploy.yml)

Статический сайт на MkDocs (тема Material) с результатами обработки записи взгляда в VR.
Задание 3: «Генераторы статических сайтов для публикации результатов исследований».

- Сайт: https://777werona-afk.github.io/vr-gaze-site/
- Автор: Кожевяткина Марина Алексеевна

## Быстрый старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make serve      # расчёт по data/raw + предпросмотр сайта
make strict     # строгая сборка, как в CI
```

Данные: положите CSV-логи взгляда (`timestamp, gaze_x, gaze_y, gaze_z, pupil, openness`) в `data/raw/`.
Если папка пуста, скрипт использует синтетические демо-данные, и сайт показывает баннер «ДЕМО-ДАННЫЕ».
Версию набора данных можно указать в файле `data/DATASET_VERSION`.

## Структура

| Путь | Назначение |
|---|---|
| `docs/` | страницы сайта |
| `scripts/analyze.py` | расчёт, таблицы, графики, метка версии, кэш |
| `scripts/make_demo_data.py` | генератор синтетических демо-данных |
| `generated/` | таблица и метка версии (создаются скриптом, не коммитятся) |
| `.github/workflows/deploy.yml` | lint → build → deploy (GitHub Pages и Cloudflare Pages) |

## Лицензии

Контент — CC BY 4.0 (`LICENSE-CONTENT.md`), код — MIT (`LICENSE`).
