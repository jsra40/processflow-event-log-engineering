from __future__ import annotations
import pandas as pd


def detect_repeated_activities(events: pd.DataFrame) -> pd.DataFrame:
    """Activity-level multiplicity: same case has the same activity more than once."""
    cols=['Source','Activity','cases_with_multiple_occurrences','events_in_affected_cases','additional_occurrences']
    if events is None or events.empty: return pd.DataFrame(columns=cols)
    counts=(events.groupby(['Source','Activity','Case_ID'],dropna=False).size().rename('occurrences').reset_index())
    multi=counts[counts['occurrences']>1].copy()
    if multi.empty: return pd.DataFrame(columns=cols)
    out=(multi.groupby(['Source','Activity'],dropna=False)
         .agg(cases_with_multiple_occurrences=('Case_ID','nunique'),
              events_in_affected_cases=('occurrences','sum'),
              additional_occurrences=('occurrences',lambda s:int((s-1).sum())))
         .reset_index())
    return out.sort_values(['Source','additional_occurrences','Activity'],ascending=[True,False,True],kind='stable').reset_index(drop=True)


def apply_multiplicity_rules(events: pd.DataFrame, rules: list[dict] | None, anchor_context: pd.DataFrame | None = None):
    """Apply explicit analyst-configured activity-specific resolution rules.

    Detection never implies deletion. Only enabled rules with action=keep_one exclude rows.
    Anchor rules retain all candidates for a case if no eligible anchor/candidate can be resolved.
    """
    if events is None or events.empty or not rules:
        return events.copy(), pd.DataFrame()
    out=events.copy().reset_index(drop=True)
    out['_Multiplicity_Order']=range(len(out))
    anchors_all=out if anchor_context is None or anchor_context.empty else pd.concat([anchor_context.copy(),out.drop(columns=['_Multiplicity_Order'])],ignore_index=True,sort=False)
    audit=[]
    drop_idx=set()
    for rule in rules:
        if not rule.get('enabled') or rule.get('action','keep_all')!='keep_one': continue
        source=rule.get('source'); activity=rule.get('activity'); strategy=rule.get('strategy','earliest')
        target=out[(out['Source'].astype(str)==str(source)) & (out['Activity'].astype(str)==str(activity)) & (~out.index.isin(drop_idx))]
        for case_id,g in target.groupby('Case_ID',sort=False):
            if len(g)<=1: continue
            chosen=None; reason=''
            if strategy=='earliest':
                chosen=g.sort_values(['Timestamp','_Multiplicity_Order'],kind='stable').index[0]; reason='Earliest occurrence retained'
            elif strategy=='latest':
                chosen=g.sort_values(['Timestamp','_Multiplicity_Order'],kind='stable').index[-1]; reason='Latest occurrence retained'
            elif strategy=='first_source_record':
                chosen=g.sort_values('_Multiplicity_Order',kind='stable').index[0]; reason='First generated source record retained'
            elif strategy=='last_source_record':
                chosen=g.sort_values('_Multiplicity_Order',kind='stable').index[-1]; reason='Last generated source record retained'
            elif strategy in {'closest_before_anchor','closest_after_anchor','closest_to_anchor'}:
                anchor_activity=rule.get('anchor_activity')
                anchors=anchors_all[(anchors_all['Case_ID']==case_id) & (anchors_all['Activity'].astype(str)==str(anchor_activity))].copy()
                if len(anchors):
                    occurrence=rule.get('anchor_occurrence','first')
                    anchors['Timestamp']=pd.to_datetime(anchors['Timestamp'],errors='coerce')
                    anchors=anchors.dropna(subset=['Timestamp']).sort_values(['Timestamp'],kind='stable')
                    if not anchors.empty:
                        anchor_ts=anchors.iloc[-1]['Timestamp'] if occurrence=='last' else anchors.iloc[0]['Timestamp']
                        cand=g.copy(); cand['_delta']=cand['Timestamp']-anchor_ts
                        if strategy=='closest_before_anchor': cand=cand[cand['_delta']<=pd.Timedelta(0)].sort_values(['_delta','_Multiplicity_Order'],ascending=[False,True],kind='stable')
                        elif strategy=='closest_after_anchor': cand=cand[cand['_delta']>=pd.Timedelta(0)].sort_values(['_delta','_Multiplicity_Order'],ascending=[True,True],kind='stable')
                        else:
                            cand['_abs_delta']=cand['_delta'].abs(); cand=cand.sort_values(['_abs_delta','_Multiplicity_Order'],kind='stable')
                        if len(cand): chosen=cand.index[0]; reason=f"{strategy.replace('_',' ')} retained relative to {anchor_activity}"
            if chosen is None:
                for idx in g.index:
                    audit.append({'Case_ID':case_id,'Source':source,'Activity':activity,'Timestamp':out.at[idx,'Timestamp'],
                                  'Source_Row_Number':out.at[idx,'Source_Row_Number'] if 'Source_Row_Number' in out.columns else None,
                                  'Decision':'KEEP','Rule':strategy,'Reason':'Rule unresolved for this case; all occurrences retained'})
                continue
            for idx in g.index:
                decision='KEEP' if idx==chosen else 'EXCLUDE'
                if decision=='EXCLUDE': drop_idx.add(idx)
                audit.append({'Case_ID':case_id,'Source':source,'Activity':activity,'Timestamp':out.at[idx,'Timestamp'],
                              'Source_Row_Number':out.at[idx,'Source_Row_Number'] if 'Source_Row_Number' in out.columns else None,
                              'Decision':decision,'Rule':strategy,'Reason':reason if decision=='KEEP' else f'Additional occurrence excluded; {reason}'})
    resolved=out.loc[~out.index.isin(drop_idx)].drop(columns=['_Multiplicity_Order']).reset_index(drop=True)
    return resolved, pd.DataFrame(audit)
