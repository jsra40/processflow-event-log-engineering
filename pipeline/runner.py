from pathlib import Path
import pandas as pd
from .config import load_project_config
from .ingestion import load_table
from .identity_vault import LocalIdentityVault
from .deidentification import apply_privacy_actions
from .mapping import apply_mapping
from .event_builder import build_events
from .integration import integrate_event_logs
from .qa import event_log_summary
from .manifest import build_manifest
from .final_privacy import final_privacy_gate
from .export import export_run
from .temporal import apply_temporal_order
from .analysis import build_process_analysis
from .multiplicity import detect_repeated_activities, apply_multiplicity_rules
from .quality import build_quality_gate, write_validation_package


def _resolve(base, value):
    p=Path(value); return p if p.is_absolute() else (base/p).resolve()

def run_project(config_path):
    config_path=Path(config_path).resolve(); base=config_path.parent.parent
    cfg=load_project_config(config_path)
    project=cfg['project']; privacy=cfg['privacy']; identity_fields=privacy.get('identity_fields',{})
    vault_root=_resolve(base,cfg.get('paths',{}).get('identity_vault','secure_local'))
    output_dir=_resolve(base,cfg.get('paths',{}).get('output','output'))
    identity_cfg=cfg.get('identity_continuity',{})
    case_mode=identity_cfg.get('population_mode','allow_new')
    vault=LocalIdentityVault(vault_root, case_mode=case_mode)
    seed_lookup=identity_cfg.get('case_lookup')
    if seed_lookup:
        vault.import_lookup(_resolve(base,seed_lookup),'case')
    logs=[]; rule_diags=[]; mapping_diags=[]; source_recon=[]; unmapped={}; inputs=[]; mappings=[]; warnings=[]; quality_issue_records=[]
    for source in cfg['sources']:
        source_path=_resolve(base,source['path']); inputs.append(source_path)
        df=load_table(source_path, sheet_name=source.get('sheet',0)).copy()
        # Stable row-level provenance for audit/traceability. 2 = first data row after a one-row header.
        df['Source_Row_Number']=range(2,len(df)+2)
        raw_rows=len(df)
        source_identity_fields=source.get('identity_fields',identity_fields)
        deid,audit=apply_privacy_actions(df,source_identity_fields,vault)
        before_population=len(deid)
        if case_mode=='existing_only' and 'Case_ID' in deid.columns:
            deid=deid[deid['Case_ID'].notna()].copy()
        population_eligible=len(deid); population_excluded=before_population-population_eligible
        recon={'source':source['name'],'raw_rows':raw_rows,'population_eligible_rows':population_eligible,
               'population_excluded_rows':population_excluded,'mapping_input_rows':population_eligible,
               'rows_after_mapping_policy':population_eligible,'rows_excluded_unmapped_policy':0,
               'inclusion_input_rows':population_eligible,'rows_after_inclusion':population_eligible,
               'rows_excluded_by_inclusion':0}
        if source.get('mapping'):
            mc=source['mapping']; mp=_resolve(base,mc['path']); mappings.append(mp)
            mdf=load_table(mp,sheet_name=mc.get('sheet',0))
            mapping_input=len(deid)
            mapping_policy=mc.get('unmapped_policy','keep')
            deid,diag=apply_mapping(deid,mdf,keys=mc.get('keys'),outputs=mc['outputs'],unmapped_policy=mapping_policy,source_keys=mc.get('source_keys'),mapping_keys=mc.get('mapping_keys'))
            after_mapping=len(deid)
            recon.update({'mapping_input_rows':mapping_input,'rows_after_mapping_policy':after_mapping,
                          'rows_excluded_unmapped_policy':mapping_input-after_mapping,'inclusion_input_rows':after_mapping})
            # Optional mapping semantics: mapping can explicitly drive activity and/or inclusion.
            include_col=mc.get('include_column')
            include_values=mc.get('include_values',[])
            before_include=len(deid)
            if include_col:
                if include_col not in deid.columns:
                    raise ValueError(f"Configured mapping inclusion column missing after mapping: {include_col}")
                allowed={str(v).strip().casefold() for v in include_values}
                deid=deid[deid[include_col].astype(str).str.strip().str.casefold().isin(allowed)].copy()
            recon.update({'rows_after_inclusion':len(deid),'rows_excluded_by_inclusion':before_include-len(deid)})
            mapping_diags.append({'source':source['name'],'rows_total':diag['rows_total'],'rows_mapped':diag['rows_mapped'],
                                  'rows_after_mapping_policy':after_mapping,'rows_excluded_unmapped_policy':mapping_input-after_mapping,
                                  'rows_after_inclusion':len(deid),'rows_excluded_by_mapping':before_include-len(deid),
                                  'rows_unmapped':diag['rows_unmapped'],'coverage':diag['coverage'],'unmapped_policy':mapping_policy})
            unmapped[source['name']]=diag['unmapped_keys']
            if diag['rows_unmapped']: warnings.append(f"{source['name']}: {diag['rows_unmapped']} unmapped rows")
        event_rules=[dict(r) for r in source.get('event_rules',[])]
        if source.get('mapping',{}).get('activity_output'):
            mapped_activity=source['mapping']['activity_output']
            for r in event_rules:
                if 'activity_value' not in r:
                    r['activity_from']=mapped_activity
        source_recon.append(recon)
        events,rdiag,rissues=build_events(deid,source['name'],event_rules,return_issue_records=True)
        logs.append(events); rdiag.insert(0,'source',source['name']); rule_diags.append(rdiag)
        if rissues is not None and not rissues.empty: quality_issue_records.append(rissues)
    integrated,idiag=integrate_event_logs(logs,cfg.get('integration',{}).get('duplicate_policy','flag'))
    repeated_before=detect_repeated_activities(integrated)
    multiplicity_rules=[]
    for source in cfg['sources']:
        for rule in source.get('multiplicity_rules',[]):
            rr=dict(rule); rr.setdefault('source',source['name']); multiplicity_rules.append(rr)
    anchor_context=pd.DataFrame()
    anchor_path=cfg.get('integration',{}).get('multiplicity_anchor_event_log')
    if anchor_path:
        anchor_context=pd.read_csv(_resolve(base,anchor_path))
        anchor_context['Timestamp']=pd.to_datetime(anchor_context['Timestamp'],errors='coerce')
    integrated,multiplicity_audit=apply_multiplicity_rules(integrated,multiplicity_rules,anchor_context=anchor_context)
    repeated_after=detect_repeated_activities(integrated)
    integrated,temporal_violations=apply_temporal_order(integrated,cfg.get('integration',{}).get('temporal_constraints',[]))
    # Temporal adjustments happen after initial integration sorting; re-sort so exported process order reflects adjusted timestamps.
    if len(integrated):
        integrated=integrated.sort_values(['Case_ID','Timestamp','Activity'],kind='stable').reset_index(drop=True)
    if len(temporal_violations):
        warnings.append(f"{len(temporal_violations)} temporal-order violation(s) require analyst review")
    gate=final_privacy_gate(integrated.columns,identity_fields)
    if not gate['ok']:
        raise ValueError(f"Final privacy gate failed: {gate['unresolved']}")
    summary=event_log_summary(integrated); summary.update({'duplicate_candidates':idiag.get('duplicates',0)})
    source_reconciliation=pd.DataFrame(source_recon)
    rule_diagnostics=pd.concat(rule_diags,ignore_index=True) if rule_diags else pd.DataFrame()
    mapping_diagnostics=pd.DataFrame(mapping_diags)
    quality_issue_records=pd.concat(quality_issue_records,ignore_index=True,sort=False) if quality_issue_records else pd.DataFrame()
    quality=build_quality_gate(integrated,source_reconciliation,rule_diagnostics,mapping_diagnostics,
                               multiplicity_audit,temporal_violations,gate)
    summary['quality_status']=quality['status']
    analysis_tables=build_process_analysis(integrated)
    qa_tables={
        'event_rule_diagnostics':rule_diagnostics,
        'mapping_diagnostics':mapping_diagnostics,
        'source_reconciliation':source_reconciliation,
        'quality_checks':quality['checks'],
        'quality_issue_records':quality_issue_records,
        'events_by_source':integrated.groupby('Source',dropna=False).size().rename('events').reset_index(),
        'events_by_activity':integrated.groupby('Activity',dropna=False).size().rename('events').reset_index(),
        'temporal_violations':temporal_violations,
        'repeated_activity_occurrences_before_resolution':repeated_before,
        'repeated_activity_occurrences_after_resolution':repeated_after,
        'multiplicity_resolution_audit':multiplicity_audit,
        'timestamp_adjustments':integrated.loc[integrated.get('Timestamp_Adjusted',False).eq(True),
            [c for c in ['Case_ID','Activity','Timestamp_Original','Timestamp','Timestamp_Precision','Timestamp_Adjustment_Reason'] if c in integrated.columns]].copy()
            if 'Timestamp_Adjusted' in integrated.columns else pd.DataFrame(),
    }
    manifest=build_manifest(project,config_path,inputs,mappings,summary,warnings)
    paths=export_run(output_dir,integrated,qa_tables,manifest,unmapped)
    validation_zip,validation_dir=write_validation_package(output_dir,quality,source_reconciliation,rule_diagnostics,
                                                           mapping_diagnostics,multiplicity_audit,temporal_violations,quality_issue_records)
    paths['validation_report']=validation_zip; paths['validation_dir']=validation_dir
    analysis_dir=Path(output_dir)/'analysis'; analysis_dir.mkdir(exist_ok=True)
    for name,table in analysis_tables.items(): table.to_csv(analysis_dir/f'{name}.csv',index=False)
    paths['analysis_dir']=str(analysis_dir)
    identity_manifest=vault.write_identity_manifest(project.get('name','Project'))
    identity_qa=pd.DataFrame([vault.stats | {'population_mode':case_mode,'identity_fingerprint':vault.identity_fingerprint('case')}])
    identity_qa.to_csv(Path(output_dir)/'qa_identity_continuity.csv',index=False)
    paths['identity_manifest']=str(identity_manifest)
    paths['identity_qa']=str(Path(output_dir)/'qa_identity_continuity.csv')
    return {'summary':summary,'warnings':warnings,'paths':paths,'privacy_gate':gate,
            'identity_stats':vault.stats,'identity_manifest':str(identity_manifest),
            'repeated_activity_occurrences':repeated_before,
            'repeated_activity_occurrences_after_resolution':repeated_after,
            'multiplicity_resolution_audit':multiplicity_audit,
            'quality_gate':quality,
            'source_reconciliation':source_reconciliation,
            'quality_issue_records':quality_issue_records,
            'available_activities':sorted(integrated['Activity'].dropna().astype(str).unique().tolist())}
