from pathlib import Path
import py_compile

def test_streamlit_app_compiles():
    app = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    py_compile.compile(str(app), doraise=True)
