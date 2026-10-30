from __future__ import annotations
from pathlib import Path
import io, zipfile
import pandas as pd

CORE={'Case_ID','Activity','Timestamp','Source','Timestamp_Original','Timestamp_Precision','Timestamp_Adjusted','Timestamp_Adjustment_Reason'}

def _safe_dt(s): return pd.to_datetime(s,errors='coerce')

def build_process_analysis(events: pd.DataFrame):
    df=events.copy()
    if len(df)==0:
        empty=pd.DataFrame()
        return {'overview':empty,'activity_coverage':empty,'activity_frequency':empty,'variants':empty,'case_duration':empty,'start_activities':empty,'end_activities':empty,'monthly_cases':empty,'attribute_summary':empty,'data_quality':empty,'definitions':_definitions()}
    df['Timestamp']=_safe_dt(df['Timestamp'])
    n_cases=df['Case_ID'].nunique(dropna=True); n_events=len(df); n_activities=df['Activity'].nunique(dropna=True)
    ordered=df.sort_values(['Case_ID','Timestamp','Activity'],kind='stable')
    grp=ordered.groupby('Case_ID',dropna=False)
    case_stats=grp['Timestamp'].agg(['min','max','count']).reset_index()
    case_stats['Duration_Days']=(case_stats['max']-case_stats['min']).dt.total_seconds()/86400
    case_stats['Events']=grp.size().values
    sequences=grp['Activity'].agg(lambda x:' → '.join(x.astype(str))).rename('Variant').reset_index()
    variants=sequences.groupby('Variant',dropna=False).size().rename('Cases').reset_index().sort_values(['Cases','Variant'],ascending=[False,True]).reset_index(drop=True)
    variants['Coverage_%']=(variants['Cases']/n_cases*100).round(2); variants.insert(0,'Variant_Rank',range(1,len(variants)+1))
    ac=df.groupby('Activity',dropna=False).agg(Events=('Case_ID','size'),Cases=('Case_ID','nunique')).reset_index()
    ac['Coverage_%']=(ac['Cases']/n_cases*100).round(2); ac['Cases_Missing']=n_cases-ac['Cases']; ac['Events_per_Participating_Case']=(ac['Events']/ac['Cases']).round(2)
    ac=ac.sort_values(['Coverage_%','Cases','Activity'],ascending=[False,False,True]).reset_index(drop=True)
    freq=ac[['Activity','Events','Cases','Events_per_Participating_Case']].copy().sort_values(['Events','Activity'],ascending=[False,True])
    starts=ordered.groupby('Case_ID').first()['Activity'].value_counts(dropna=False).rename_axis('Activity').reset_index(name='Cases'); starts['Coverage_%']=(starts.Cases/n_cases*100).round(2)
    ends=ordered.groupby('Case_ID').last()['Activity'].value_counts(dropna=False).rename_axis('Activity').reset_index(name='Cases'); ends['Coverage_%']=(ends.Cases/n_cases*100).round(2)
    valid=case_stats['Duration_Days'].dropna()
    overview_rows=[
      ('Cases',n_cases,'Unique Case_ID values in the final event log.'),('Events',n_events,'Total event records.'),('Activities',n_activities,'Unique activity labels.'),('Process variants',len(variants),'Unique ordered activity sequences.'),
      ('Events per case - mean',round(n_events/n_cases,2) if n_cases else None,'Average number of events per case.'),('Events per case - median',round(case_stats.Events.median(),2),'Median number of events per case.'),
      ('Case duration days - median',round(valid.median(),2) if len(valid) else None,'Median elapsed time from first to last timestamp per case.'),('Case duration days - mean',round(valid.mean(),2) if len(valid) else None,'Mean elapsed time from first to last timestamp per case.'),
      ('Case duration days - P25',round(valid.quantile(.25),2) if len(valid) else None,'25th percentile of case throughput time.'),('Case duration days - P75',round(valid.quantile(.75),2) if len(valid) else None,'75th percentile of case throughput time.'),('Case duration days - P90',round(valid.quantile(.90),2) if len(valid) else None,'90th percentile of case throughput time.'),
      ('Date range start',df.Timestamp.min(),'Earliest valid event timestamp.'),('Date range end',df.Timestamp.max(),'Latest valid event timestamp.')]
    overview=pd.DataFrame(overview_rows,columns=['Metric','Value','Definition'])
    monthly=ordered.dropna(subset=['Timestamp']).copy(); monthly['Month']=monthly.Timestamp.dt.to_period('M').astype(str)
    first_month=monthly.groupby('Case_ID').first().reset_index().groupby('Month').size().rename('Cases_Started').reset_index()
    last_month=monthly.groupby('Case_ID').last().reset_index().groupby('Month').size().rename('Cases_Ended').reset_index()
    monthly_cases=first_month.merge(last_month,on='Month',how='outer').fillna(0).sort_values('Month')
    # Attribute summary: preserved non-core fields, summarized rather than domain-interpreted.
    attrs=[]
    for col in [c for c in df.columns if c not in CORE]:
        nonnull=df[['Case_ID',col]].dropna()
        if len(nonnull)==0: continue
        case_vals=nonnull.drop_duplicates(['Case_ID',col])
        vals=case_vals[col].astype(str).value_counts().head(25)
        for val,count in vals.items(): attrs.append({'Attribute':col,'Value':val,'Cases':int(count),'Case_Coverage_%':round(count/n_cases*100,2)})
    attribute_summary=pd.DataFrame(attrs)
    missing_ts=int(df.Timestamp.isna().sum()); one_event=int((case_stats.Events==1).sum())
    dq=[('Events with missing/unparseable timestamp',missing_ts,round(missing_ts/n_events*100,2) if n_events else 0,'Review source timestamp completeness/format.'),('Cases with only one event',one_event,round(one_event/n_cases*100,2) if n_cases else 0,'Single-event cases have no measurable end-to-end throughput time.')]
    if 'Timestamp_Adjusted' in df.columns:
        adj=df['Timestamp_Adjusted'].astype(str).str.lower().isin(['true','1','yes']).sum(); dq.append(('Events with temporal timestamp adjustment',int(adj),round(adj/n_events*100,2) if n_events else 0,'Timestamp was adjusted by an approved temporal-order rule.'))
    data_quality=pd.DataFrame(dq,columns=['Check','Count','Percent','Interpretation'])
    return {'overview':overview,'activity_coverage':ac,'activity_frequency':freq,'variants':variants,'case_duration':case_stats.rename(columns={'min':'First_Timestamp','max':'Last_Timestamp'}),'start_activities':starts,'end_activities':ends,'monthly_cases':monthly_cases,'attribute_summary':attribute_summary,'data_quality':data_quality,'definitions':_definitions()}

def _definitions():
    rows=[
      ('Activity Coverage (%)','Unique cases containing an activity at least once divided by all unique cases in the final event log × 100.'),
      ('Cases Missing','Total cases minus cases containing the activity.'),('Events per Participating Case','Number of events for an activity divided by cases containing that activity.'),
      ('Process Variant','A unique ordered sequence of activity labels followed by one or more cases.'),('Case Duration','Elapsed time between a case’s earliest and latest valid event timestamps.'),
      ('Start Activity','First activity after ordering each case by timestamp.'),('End Activity','Last activity after ordering each case by timestamp.'),
      ('Attribute Case Coverage','Cases associated with an attribute value divided by all cases. A case can appear under multiple values if the attribute changes during the case.'),
      ('Important interpretation note','Low or high coverage is not automatically a data-quality problem. It may reflect process pathway differences, mapping/filtering choices, or missing data and should be reviewed with an SME.')]
    return pd.DataFrame(rows,columns=['Term','Definition'])

def analysis_csv_package(analysis: dict) -> bytes:
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:
        for name,df in analysis.items(): z.writestr(f'{name}.csv',df.to_csv(index=False))
        z.writestr('README.txt','Automatic Process Analysis\n\nThese descriptive metrics summarize the final de-identified event log. They do not define business KPIs or determine whether pathway differences are appropriate. Review findings with the relevant domain expert.\n')
    return bio.getvalue()
