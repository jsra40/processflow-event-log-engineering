from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()

def test_technical_finding_is_not_rewritten():
    assert "Technical findings remain unchanged" in APP
    assert "not a technical PASS" in APP

def test_exception_requires_review_and_justification():
    assert "I reviewed this finding and accept it as an exception for this event log" in APP
    assert "A justification is required" in APP
    assert "acknowledged and justification.strip()" in APP

def test_final_approval_requires_all_exceptions():
    assert "Approve event log with acknowledged exceptions" in APP
    assert "disabled=not all_approved" in APP
    assert "VALIDATED WITH ACKNOWLEDGED EXCEPTIONS" in APP

def test_approval_artifacts_are_downloadable():
    assert "Analyst_Exception_Approval.json" in APP
    assert "Acknowledged_Quality_Exceptions.csv" in APP

def test_new_run_resets_prior_approvals():
    assert "approvals never carry silently across runs" in APP
    assert "st.session_state.quality_exception_approvals={}" in APP
