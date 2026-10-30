
from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text()

def test_event_logs_cannot_survive_in_source_configs():
    assert "st.session_state.source_configs.pop(name,None)" in APP
    assert "if configured_name not in active_raw:" in APP
    assert "st.session_state.source_configs.pop(configured_name,None)" in APP

def test_validation_only_checks_raw_sources():
    assert "for name in raw_sources:" in APP
    assert "spec=st.session_state.source_configs.get(name)" in APP

def test_table_loading_is_cached():
    assert "@st.cache_data(show_spinner=False)" in APP
    assert "def cached_load_table(path, sheet):" in APP
