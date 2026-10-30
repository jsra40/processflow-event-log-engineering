import pandas as pd
from pipeline.quality import build_quality_gate, augment_incremental_quality


def _base_events():
    return pd.DataFrame({'Case_ID':['P000001'],'Activity':['A'],'Timestamp':[pd.Timestamp('2026-01-01')],'Source':['s']})


def test_quality_gate_passes_when_every_row_reconciles():
    src=pd.DataFrame([{'source':'s','raw_rows':2,'population_eligible_rows':1,'population_excluded_rows':1,
                       'mapping_input_rows':1,'rows_after_mapping_policy':1,'rows_excluded_unmapped_policy':0,
                       'inclusion_input_rows':1,'rows_after_inclusion':1,'rows_excluded_by_inclusion':0}])
    rules=pd.DataFrame([{'source':'s','rule':'r','eligible_rows':1,'events_created':1,'invalid_timestamps':0,'missing_case_id':0,'missing_activity':0}])
    q=build_quality_gate(_base_events(),src,rules,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{'ok':True})
    assert q['status']=='PASS'
    assert not (q['checks']['status']=='FAIL').any()


def test_invalid_timestamp_is_hard_quality_failure_even_when_accounted():
    src=pd.DataFrame([{'source':'s','raw_rows':2,'population_eligible_rows':2,'population_excluded_rows':0,
                       'mapping_input_rows':2,'rows_after_mapping_policy':2,'rows_excluded_unmapped_policy':0,
                       'inclusion_input_rows':2,'rows_after_inclusion':2,'rows_excluded_by_inclusion':0}])
    rules=pd.DataFrame([{'source':'s','rule':'r','eligible_rows':2,'events_created':1,'invalid_timestamps':1,'missing_case_id':0,'missing_activity':0}])
    q=build_quality_gate(_base_events(),src,rules,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{'ok':True})
    assert q['status']=='FAIL'
    assert 'invalid_timestamp_loss' in set(q['checks'].loc[q['checks'].status=='FAIL','check_id'])


def test_incremental_gate_proves_baseline_plus_added_equals_final():
    q={'status':'PASS','checks':pd.DataFrame([{'check_id':'x','category':'x','status':'PASS','source':None,'rule':None,'observed':0,'expected':0,'message':'ok'}]),
       'summary':pd.DataFrame()}
    combined=pd.DataFrame({'Case_ID':['P1','P1'],'Activity':['A','B'],'Timestamp':[pd.Timestamp('2026-01-01'),pd.Timestamp('2026-01-02')],'Source':['old','new']})
    out=augment_incremental_quality(q,combined,{'baseline_events':1,'new_unique_events_added':1,'final_events':2})
    assert out['status']=='PASS'
    row=out['checks'][out['checks'].check_id=='incremental_event_reconciliation'].iloc[0]
    assert row.status=='PASS'

def test_generated_events_carry_source_row_provenance(tmp_path):
    from pipeline.event_builder import build_events
    df=pd.DataFrame({'Case_ID':['P1','P2'],'When':['2026-01-01','2026-01-02'],'Source_Row_Number':[2,3]})
    ev,diag=build_events(df,'s',[{'name':'r','timestamp_from':'When','activity_value':'A','attributes':[]}])
    assert ev['Source_Row_Number'].tolist()==[2,3]
