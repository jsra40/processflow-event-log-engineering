import pandas as pd
from pipeline.event_builder import build_events

def test_invalid_timestamp_returns_source_record_for_drilldown():
    df=pd.DataFrame({
        'Case_ID':['P1','P2'],
        'When':['2026-01-01',None],
        'Source_Row_Number':[2,3],
        'Other':['ok','investigate']
    })
    ev,diag,issues=build_events(df,'ICP',[{'name':'diagnosis','timestamp_from':'When','activity_value':'Diagnosis date','attributes':['Other']}],return_issue_records=True)
    assert len(ev)==1
    assert diag.iloc[0]['invalid_timestamps']==1
    assert len(issues)==1
    row=issues.iloc[0]
    assert row['Source_Row_Number']==3
    assert row['Quality_Issue']=='invalid_timestamp_loss'
    assert row['Timestamp_Field']=='When'
    assert row['Other']=='investigate'

def test_default_build_events_api_remains_backward_compatible():
    df=pd.DataFrame({'Case_ID':['P1'],'When':['2026-01-01']})
    result=build_events(df,'S',[{'timestamp_from':'When','activity_value':'A'}])
    assert len(result)==2
