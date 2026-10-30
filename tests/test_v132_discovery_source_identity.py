from pathlib import Path
BRIDGE=(Path(__file__).resolve().parents[1]/'pipeline'/'ui_bridge.py').read_text()
APP=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()

def test_discovery_gets_stable_ui_source_identity():
    assert "internal_to_ui=" in BRIDGE
    assert "table['UI_Source']=" in BRIDGE
    assert "'repeated_activity_occurrences'" in BRIDGE

def test_resolution_panel_prefers_ui_source_identity():
    assert "group_col='UI_Source'" in APP
    assert "ui_name=str(source_value)" in APP
    assert "Triggered by the last successful run:" in APP
