# OpsLens tasks. On Windows run with:  mingw32-make <target>   (or `make` if installed)
# Every target is one plain command, so you can also copy it and run it by hand.

ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: help setup data ping test gen eval serve demo

help:
	@echo setup  - create .venv and install requirements
	@echo data   - download public datasets (Bitext, UCI) into data/public
	@echo ping   - send one small JSON request to each LLM provider
	@echo test   - run all tests
	@echo gen    - generate the 56-day operations dataset (M2)
	@echo eval   - reproduce every number into eval/results.json (M8)
	@echo serve  - run the dashboard server (M9)
	@echo demo   - serve from cached results, no network (M11)

setup:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt

data:
	$(PY) scripts/download_data.py

ping:
	$(PY) scripts/ping_llm.py

test:
	$(PY) -m pytest -q

gen:
	$(PY) data/generate_ops.py

eval:
	$(PY) eval/run_eval.py

serve:
	$(PY) -m uvicorn server.app:app --port 8000

demo:
	$(PY) -m server.demo
