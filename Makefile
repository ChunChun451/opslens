ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: help setup data ping test gen eval serve demo seed load eval-local

help:
	@echo setup  - create .venv and install requirements
	@echo data   - download public datasets (Bitext, UCI) into data/public
	@echo ping   - send one small JSON request to each LLM provider
	@echo test   - run all tests
	@echo gen    - generate the 56-day operations dataset
	@echo eval   - reproduce every number into eval/results.json
	@echo serve  - run the dashboard server
	@echo demo   - serve from cached results, no network
	@echo seed   - create the Postgres tables and demo users
	@echo load   - load a million tickets into a scratch database and time it
	@echo eval-local - score the local Ollama model on the recorded classification test

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

seed:
	$(PY) -m opslens.seed

load:
	$(PY) scripts/load_test.py

eval-local:
	$(PY) scripts/eval_local_llm.py
