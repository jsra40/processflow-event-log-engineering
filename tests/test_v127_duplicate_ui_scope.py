from pathlib import Path

def test_duplicate_inspection_uses_completed_run_state():
    t=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()
    assert "r=st.session_state.run_result" in t
    assert "dup_df=r.get('duplicate_inspection')" in t
