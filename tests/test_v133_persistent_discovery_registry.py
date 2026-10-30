from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()
def test_registry_default(): assert "'multiplicity_discovery':[]" in APP
def test_run_persists_registry(): assert "st.session_state.multiplicity_discovery=_disc.to_dict('records')" in APP
def test_events_reads_registry(): assert "registry=st.session_state.get('multiplicity_discovery',[])" in APP
def test_results_confirms_trigger(): assert "Configuration trigger saved:" in APP
def test_absent_trigger_is_visible(): assert "no discovery trigger is currently stored" in APP
