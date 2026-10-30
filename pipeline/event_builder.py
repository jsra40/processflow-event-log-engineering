import pandas as pd
from .temporal import infer_timestamp_precision

CANONICAL_REQUIRED=['Case_ID','Activity','Timestamp','Source']

def _resolve_activity(df, rule):
    if 'activity_value' in rule: base=pd.Series(rule['activity_value'],index=df.index,dtype='object')
    else:
        col=rule.get('activity_from')
        if not col or col not in df.columns: raise ValueError(f'Invalid activity_from: {col}')
        base=df[col].astype('object')
    prefix=str(rule.get('activity_prefix','') or '').strip()
    suffix=str(rule.get('activity_suffix','') or '').strip()
    if prefix or suffix:
        def compose(value):
            if pd.isna(value): return value
            parts=[x for x in (prefix,str(value).strip(),suffix) if x]
            return ' '.join(parts)
        base=base.map(compose)
    return base

def build_events(df, source_name, event_rules, return_issue_records=False):
    logs=[]; diagnostics=[]; issue_records=[]
    for i,rule in enumerate(event_rules,1):
        ts=rule.get('timestamp_from')
        if ts not in df.columns: raise ValueError(f'Event rule {i}: timestamp column missing: {ts}')
        work=df.copy()
        # Simple equality/inclusion filters for V0.2.
        for col,val in rule.get('where',{}).items():
            if col not in work.columns: raise ValueError(f'Event rule {i}: filter column missing: {col}')
            work=work[work[col].isin(val if isinstance(val,list) else [val])]
        filtered_rows=len(work)
        raw_timestamp=work[ts].copy()
        precision=raw_timestamp.map(infer_timestamp_precision)
        parsed=pd.to_datetime(raw_timestamp, errors='coerce')
        invalid_mask=parsed.isna(); invalid=int(invalid_mask.sum())
        if invalid:
            bad=work.loc[invalid_mask].copy()
            bad['Quality_Issue']='invalid_timestamp_loss'
            bad['Quality_Reason']='Timestamp is missing or cannot be parsed'
            bad['Event_Rule']=rule.get('name',f'rule_{i}')
            bad['Timestamp_Field']=ts
            bad['Timestamp_Original_Value']=raw_timestamp.loc[invalid_mask].values
            bad['Intended_Activity']=_resolve_activity(bad,rule).values
            bad['Source']=source_name
            issue_records.append(bad)
        keep=~invalid_mask
        work=work.loc[keep].copy(); parsed=parsed.loc[keep]; raw_timestamp=raw_timestamp.loc[keep]; precision=precision.loc[keep]
        if 'Case_ID' not in work.columns: raise ValueError('De-identified Case_ID is required before event generation')
        activity=_resolve_activity(work,rule)
        missing_case_mask=work['Case_ID'].isna()
        missing_case=int(missing_case_mask.sum())
        if missing_case:
            bad=work.loc[missing_case_mask].copy()
            bad['Quality_Issue']='missing_case_loss'
            bad['Quality_Reason']='Case_ID is missing after identity/de-identification processing'
            bad['Event_Rule']=rule.get('name',f'rule_{i}')
            bad['Timestamp_Field']=ts
            bad['Timestamp_Original_Value']=raw_timestamp.loc[missing_case_mask].values
            bad['Intended_Activity']=_resolve_activity(bad,rule).loc[missing_case_mask].values
            bad['Source']=source_name
            issue_records.append(bad)
        # Count missing Activity only after timestamp and Case_ID are valid so every row has one loss reason.
        missing_activity_mask=(~missing_case_mask) & activity.isna()
        missing_activity=int(missing_activity_mask.sum())
        if missing_activity:
            bad=work.loc[missing_activity_mask].copy()
            bad['Quality_Issue']='missing_activity_loss'
            bad['Quality_Reason']='Activity is missing after activity resolution'
            bad['Event_Rule']=rule.get('name',f'rule_{i}')
            bad['Timestamp_Field']=ts
            bad['Timestamp_Original_Value']=raw_timestamp.loc[missing_activity_mask].values
            bad['Intended_Activity']=activity.loc[missing_activity_mask].values
            bad['Source']=source_name
            issue_records.append(bad)
        valid=(~missing_case_mask) & (~activity.isna())
        valid_work=work.loc[valid].copy(); valid_parsed=parsed.loc[valid]; valid_raw=raw_timestamp.loc[valid]; valid_precision=precision.loc[valid]; valid_activity=activity.loc[valid]
        ev=pd.DataFrame({'Case_ID':valid_work['Case_ID'].values,
                         'Activity':valid_activity.values,
                         'Timestamp':valid_parsed.values,
                         'Timestamp_Original':valid_raw.values,
                         'Timestamp_Precision':valid_precision.values,
                         'Source':source_name})
        if 'Source_Row_Number' in valid_work.columns:
            ev['Source_Row_Number']=valid_work['Source_Row_Number'].values
        for attr in rule.get('attributes',[]):
            if attr not in valid_work.columns: raise ValueError(f'Event rule {i}: attribute missing: {attr}')
            ev[attr]=valid_work[attr].values
        ev['Event_Rule']=rule.get('name',f'rule_{i}')
        logs.append(ev)
        diagnostics.append({'rule':rule.get('name',f'rule_{i}'),'input_rows':len(df),'eligible_rows':filtered_rows,
                            'events_created':len(ev),'invalid_timestamps':invalid,'missing_case_id':missing_case,
                            'missing_activity':missing_activity,'accounted_rows':len(ev)+invalid+missing_case+missing_activity})
    events=pd.concat(logs,ignore_index=True,sort=False) if logs else pd.DataFrame(columns=CANONICAL_REQUIRED)
    issues=(pd.concat(issue_records,ignore_index=True,sort=False) if issue_records else pd.DataFrame())
    return (events,pd.DataFrame(diagnostics),issues) if return_issue_records else (events,pd.DataFrame(diagnostics))

def validate_canonical_events(events):
    missing=[c for c in CANONICAL_REQUIRED if c not in events.columns]
    issues=[]
    if missing: issues.append(f'Missing canonical columns: {missing}')
    else:
        for c in ['Case_ID','Activity','Timestamp']:
            n=int(events[c].isna().sum())
            if n: issues.append(f'{c} contains {n} missing values')
    return {'ok':not issues,'issues':issues,'rows':len(events)}
