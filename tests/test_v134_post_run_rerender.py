from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()

def test_successful_run_forces_fresh_streamlit_render():
    assert "st.rerun()" in APP
    assert "tab contents earlier in this script were rendered" in APP

def test_post_run_notice_survives_forced_rerun():
    assert "'post_run_notice':None" in APP
    assert "st.session_state.post_run_notice=(" in APP
    assert "Events & mappings can display the new controls" in APP

def test_discovery_is_saved_before_rerun():
    save=APP.index("st.session_state.multiplicity_discovery=_disc.to_dict('records')")
    rerun=APP.index("st.rerun()")
    assert save < rerun
