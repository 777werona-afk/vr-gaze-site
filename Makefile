.PHONY: all data site serve strict clean bench

PY ?= python3
RAW := $(wildcard data/raw/*.csv)

all: strict

# шаг 1: расчёт по данным (кэш внутри скрипта — по хешу данных, кода и параметров)
data:
	$(PY) scripts/analyze.py

# шаг 2: сборка сайта; зависит от расчёта, поэтому графики всегда актуальны
site: data
	mkdocs build

# строгая сборка (битые ссылки и предупреждения = ошибка), как в CI
strict: data
	mkdocs build --strict

serve: data
	mkdocs serve

# замер выигрыша от кэша: холодный и тёплый запуск
bench:
	$(PY) scripts/analyze.py --force
	$(PY) scripts/analyze.py

clean:
	rm -rf site results/.cache.json generated docs/assets/generated
