
from pathlib import Path

def test_input_type_is_selected_at_source_registration():
    t=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text()
    assert "['Raw source data','Existing standardized event log']" in t
    assert "event_log_sources=" in t
    assert "raw_sources=" in t
    assert "Event log ready:" in t

def test_removed_upload_purges_derived_state():
    t=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text()
    assert "stale=set(st.session_state.sources)-uploaded_names" in t
    assert "st.session_state.source_configs.pop(stale_name,None)" in t
    assert "st.session_state.privacy_decisions.pop(k,None)" in t

def test_raw_configuration_loops_exclude_event_logs():
    t=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text()
    # Privacy and generic Events sections are explicitly driven by raw_sources.
    assert t.count("for name,item in raw_sources.items():") >= 2
