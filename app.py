# app.py (repo root) — Streamlit/HF entrypoint
import runpy

# Run the real Streamlit app module exactly like:
# streamlit run src/olympus/ui/app.py
runpy.run_module("olympus.ui.app", run_name="__main__")
