from __future__ import annotations
from pathlib import Path
import json, zipfile
import pandas as pd


def _check(check_id, category, status, message, observed=None, expected=None, source=None, rule=None):
    return {'check_id':check_id,'category':category,'status':status,'source':source,'rule':rule,
            'observed':observed,'expected':expected,'message':message}


def build_quality_gate(events, source_reconciliation, rule_diagnostics, mapping_diagnostics,
                       multiplicity_audit=None, temporal_violations=None, privacy_gate=None):
    checks=[]
    events=events if events is not None else pd.DataFrame()
    source_reconciliation=source_reconciliation if source_reconciliation is not None else pd.DataFrame()
    rule_diagnostics=rule_diagnostics if rule_diagnostics is not None else pd.DataFrame()
    mapping_diagnostics=mapping_diagnostics if mapping_diagnostics is not None else pd.DataFrame()
    multiplicity_audit=multiplicity_audit if multiplicity_audit is not None else pd.DataFrame()
    temporal_violations=temporal_violations if temporal_violations is not None else pd.DataFrame()

    # Canonical event integrity: these are hard requirements for a trustworthy process-mining log.
    for col in ['Case_ID','Activity','Timestamp','Source']:
        if col not in events.columns:
            checks.append(_check(f'canonical_{col}','Final event integrity','FAIL',f'Required canonical column {col} is missing.',0,1))
        else:
            missing=int(events[col].isna().sum())
            checks.append(_check(f'canonical_{col}','Final event integrity','PASS' if missing==0 else 'FAIL',
                                 f'{missing:,} final events have missing {col}.',missing,0))

    # Every source row must be accounted for at the population/mapping/inclusion stages.
    for _,r in source_reconciliation.iterrows():
        raw=int(r.get('raw_rows',0)); pop=int(r.get('population_eligible_rows',0)); pop_ex=int(r.get('population_excluded_rows',0))
        ok=(raw==pop+pop_ex)
        checks.append(_check('source_population_reconciliation','Source reconciliation','PASS' if ok else 'FAIL',
                             f'{raw:,} raw rows = {pop:,} population-eligible + {pop_ex:,} excluded.',raw,pop+pop_ex,r.get('source')))
        map_in=int(r.get('mapping_input_rows',pop)); map_after=int(r.get('rows_after_mapping_policy',map_in)); map_drop=int(r.get('rows_excluded_unmapped_policy',0))
        ok2=(map_in==map_after+map_drop)
        checks.append(_check('mapping_policy_reconciliation','Source reconciliation','PASS' if ok2 else 'FAIL',
                             f'{map_in:,} mapping-input rows = {map_after:,} retained + {map_drop:,} excluded by unmapped policy.',map_in,map_after+map_drop,r.get('source')))
        inc_in=int(r.get('inclusion_input_rows',map_after)); inc_after=int(r.get('rows_after_inclusion',inc_in)); inc_ex=int(r.get('rows_excluded_by_inclusion',0))
        ok3=(inc_in==inc_after+inc_ex)
        checks.append(_check('mapping_inclusion_reconciliation','Source reconciliation','PASS' if ok3 else 'FAIL',
                             f'{inc_in:,} inclusion-input rows = {inc_after:,} retained + {inc_ex:,} explicitly excluded.',inc_in,inc_after+inc_ex,r.get('source')))

    # Per event rule, filtered source rows must equal created events plus explicit invalid/missing reasons.
    for _,r in rule_diagnostics.iterrows():
        eligible=int(r.get('eligible_rows',0)); created=int(r.get('events_created',0)); invalid=int(r.get('invalid_timestamps',0))
        miss_case=int(r.get('missing_case_id',0)); miss_act=int(r.get('missing_activity',0)); accounted=created+invalid+miss_case+miss_act
        ok=(eligible==accounted)
        src=r.get('source'); rule=r.get('rule')
        checks.append(_check('event_rule_reconciliation','Event generation','PASS' if ok else 'FAIL',
                             f'{eligible:,} rule-eligible rows = {created:,} events + {invalid:,} invalid timestamps + {miss_case:,} missing Case_ID + {miss_act:,} missing Activity.',eligible,accounted,src,rule))
        if invalid:
            checks.append(_check('invalid_timestamp_loss','Event generation','FAIL',f'{invalid:,} eligible rows could not create events because their timestamp was missing/unparseable.',invalid,0,src,rule))
        if miss_case:
            checks.append(_check('missing_case_loss','Event generation','FAIL',f'{miss_case:,} timestamp-valid rows could not create events because Case_ID was missing.',miss_case,0,src,rule))
        if miss_act:
            checks.append(_check('missing_activity_loss','Event generation','FAIL',f'{miss_act:,} otherwise-valid rows could not create events because Activity was missing.',miss_act,0,src,rule))

    # Mapping coverage is a review signal, but explicit drop/keep policies make it explainable rather than silent loss.
    for _,r in mapping_diagnostics.iterrows():
        unmapped=int(r.get('rows_unmapped',0)); policy=str(r.get('unmapped_policy','keep'))
        status='PASS' if unmapped==0 else 'WARN'
        checks.append(_check('mapping_coverage','Mapping quality',status,
                             f'{unmapped:,} rows were unmapped; configured policy: {policy}.',unmapped,0,r.get('source')))

    excluded=0 if multiplicity_audit.empty or 'Decision' not in multiplicity_audit else int((multiplicity_audit['Decision']=='EXCLUDE').sum())
    checks.append(_check('multiplicity_audit','Multiplicity','PASS',f'{excluded:,} occurrences were excluded by explicit activity-specific multiplicity rules and are audit-traceable.',excluded,excluded))

    tv=len(temporal_violations)
    checks.append(_check('temporal_violations','Temporal quality','PASS' if tv==0 else 'WARN',
                         f'{tv:,} temporal-order violations require analyst review.' if tv else 'No unresolved temporal-order violations detected.',tv,0))

    privacy_ok=bool((privacy_gate or {}).get('ok',False))
    checks.append(_check('privacy_gate','Privacy','PASS' if privacy_ok else 'FAIL',
                         'Final privacy gate passed.' if privacy_ok else 'Final privacy gate did not pass.',int(privacy_ok),1))

    checks_df=pd.DataFrame(checks)
    fail_count=int((checks_df.status=='FAIL').sum()) if len(checks_df) else 0
    warn_count=int((checks_df.status=='WARN').sum()) if len(checks_df) else 0
    status='FAIL' if fail_count else ('WARN' if warn_count else 'PASS')
    summary=pd.DataFrame([{'quality_status':status,'checks_total':len(checks_df),'checks_passed':int((checks_df.status=='PASS').sum()),
                           'warnings':warn_count,'failures':fail_count,'final_events':len(events),
                           'final_cases':int(events['Case_ID'].nunique()) if 'Case_ID' in events else 0}])
    return {'status':status,'checks':checks_df,'summary':summary}


def write_validation_package(output_dir, quality, source_reconciliation, rule_diagnostics, mapping_diagnostics,
                             multiplicity_audit=None, temporal_violations=None, quality_issue_records=None):
    out=Path(output_dir); report=out/'validation_report'; report.mkdir(parents=True,exist_ok=True)
    tables={
        'Quality_Summary.csv':quality['summary'], 'Quality_Checks.csv':quality['checks'],
        'Source_Reconciliation.csv':source_reconciliation, 'Event_Rule_Reconciliation.csv':rule_diagnostics,
        'Mapping_QA.csv':mapping_diagnostics,
        'Multiplicity_QA.csv':multiplicity_audit if multiplicity_audit is not None else pd.DataFrame(),
        'Temporal_QA.csv':temporal_violations if temporal_violations is not None else pd.DataFrame(),
        'Affected_Quality_Records.csv':quality_issue_records if quality_issue_records is not None else pd.DataFrame(),
    }
    for name,df in tables.items(): df.to_csv(report/name,index=False)
    (report/'README.txt').write_text(
        'EVENT LOG VALIDATION REPORT\n\nPASS = all hard integrity/reconciliation checks passed and no review warnings.\n'
        'WARN = hard checks passed, but one or more review signals remain.\nFAIL = at least one hard integrity/reconciliation check failed.\n\n'
        'A quality gate validates technical execution and accounting. It does not prove that analyst-selected domain-specific rules are correct for the domain.\n',encoding='utf-8')
    zip_path=out/'Event_Log_Validation_Report.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in report.iterdir():
            if p.is_file(): z.write(p,p.name)
    return str(zip_path), str(report)

def augment_incremental_quality(quality, combined, incremental):
    checks=quality['checks'].copy()
    extra=[]
    baseline=int(incremental.get('baseline_events',0)); added=int(incremental.get('new_unique_events_added',0)); final=int(incremental.get('final_events',0))
    ok=(baseline+added==final)
    extra.append(_check('incremental_event_reconciliation','Incremental integration','PASS' if ok else 'FAIL',
                        f'{baseline:,} baseline events preserved + {added:,} incoming events added = {final:,} final events.',final,baseline+added))
    for col in ['Case_ID','Activity','Timestamp','Source']:
        missing=int(combined[col].isna().sum()) if col in combined.columns else len(combined)
        extra.append(_check(f'incremental_final_{col}','Final event integrity','PASS' if col in combined.columns and missing==0 else 'FAIL',
                            f'{missing:,} combined final events have missing {col}.',missing,0))
    checks=pd.concat([checks,pd.DataFrame(extra)],ignore_index=True)
    failures=int((checks.status=='FAIL').sum()); warnings=int((checks.status=='WARN').sum())
    status='FAIL' if failures else ('WARN' if warnings else 'PASS')
    summary=pd.DataFrame([{'quality_status':status,'checks_total':len(checks),'checks_passed':int((checks.status=='PASS').sum()),
                           'warnings':warnings,'failures':failures,'final_events':len(combined),
                           'final_cases':int(combined['Case_ID'].nunique()) if 'Case_ID' in combined else 0}])
    return {'status':status,'checks':checks,'summary':summary}
