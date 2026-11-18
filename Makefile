.PHONY: smoke test eval dashboard gradio clean

PYTHON ?= python3

smoke:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/smoke_repo.py

test: smoke

eval:
	ASSISTANT_OUTPUT_DIR=outputs/local PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/run_before_after_eval.py

dashboard:
	streamlit run app/streamlit_dashboard.py

gradio:
	$(PYTHON) -m app.gradio_demo

clean:
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find outputs/local -type f ! -name '.gitkeep' -delete
