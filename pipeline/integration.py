import pandas as pd
from .event_builder import validate_canonical_events

def integrate_event_logs(event_logs, duplicate_policy='flag'):
    if not event_logs: return pd.DataFrame(), {'rows':0,'duplicates':0}
    for e in event_logs:
        check=validate_canonical_events(e)
        if not check['ok']: raise ValueError('; '.join(check['issues']))
    out=pd.concat(event_logs,ignore_index=True,sort=False)
    key=['Case_ID','Activity','Timestamp','Source']
    dup=out.duplicated(key,keep=False)
    n=int(dup.sum())
    if duplicate_policy=='drop': out=out.drop_duplicates(key,keep='first')
    elif duplicate_policy=='error' and n: raise ValueError(f'{n} duplicate candidate event rows detected')
    elif duplicate_policy!='flag': raise ValueError('duplicate_policy must be flag, drop, or error')
    if duplicate_policy=='flag': out['Duplicate_Candidate']=dup
    out=out.sort_values(['Case_ID','Timestamp','Activity'],kind='stable').reset_index(drop=True)
    return out, {'rows':len(out),'duplicates':n,'cases':int(out['Case_ID'].nunique()),'activities':int(out['Activity'].nunique())}
