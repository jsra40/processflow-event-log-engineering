from pathlib import Path

def test_results_uses_persisted_run_result_for_duplicate_inspection():
    text=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()
    assert "dup_df=r.get('duplicate_inspection')" in text
    assert "result.get('duplicate_inspection') if 'result' in locals()" not in text

def test_results_duplicate_metric_uses_incremental_duplicates():
    text=(Path(__file__).resolve().parents[1]/'ui'/'app.py').read_text()
    assert "incremental.get('incoming_duplicates_within_batch',0)" in text
    assert "d.metric('Repeated signatures (QA)',duplicate_metric)" in text
