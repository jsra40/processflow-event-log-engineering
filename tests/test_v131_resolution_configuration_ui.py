from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()

def test_post_run_resolution_panel_is_visible_and_explicit():
    assert "Configure repeated activity occurrences" in APP
    assert "Handle multiple occurrences for this activity" in APP
    assert "After changing a rule, go to **Validate & run** and run the pipeline again." in APP

def test_activity_specific_rules_include_expected_strategies():
    for label in [
        "Earliest occurrence","Latest occurrence",
        "Closest before another activity","Closest after another activity",
        "Closest to another activity","First source record","Last source record"
    ]:
        assert label in APP

def test_resolution_panel_writes_back_to_source_config():
    assert "cfg['multiplicity_rules']=list(existing.values())" in APP
    assert "st.session_state.source_configs[ui_name]=cfg" in APP
