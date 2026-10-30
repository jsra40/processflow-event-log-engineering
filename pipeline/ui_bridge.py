from __future__ import annotations
from pathlib import Path
import json, zipfile
import pandas as pd
import yaml
from .runner import run_project
from .ingestion import load_table
from .final_privacy import final_privacy_gate
from .qa import event_log_summary
from .manifest import build_manifest
from .export import export_run
from .analysis import build_process_analysis
from .quality import augment_incremental_quality, write_validation_package

ACTION_MAP={'Keep':'keep','Pseudonymize':'pseudonymize','Remove':'remove','Keep with approved justification':'keep','Transformation only':'transformation_only'}
SAFE_SUFFIX='_ID'

def privacy_target(column, decision, is_case=False):
    if is_case: return 'Case_ID'
    return f'{column}{SAFE_SUFFIX}' if decision=='Pseudonymize' else column

def _rewrite_after_privacy(value, privacy_decisions, case_column=None):
    if value==case_column: return 'Case_ID'
    return privacy_target(value,privacy_decisions.get(value)) if value else value

def _decisions_for_spec(privacy_decisions, spec):
    """Return column decisions for one source without cross-source collisions."""
    source_label=spec.get('ui_source_name') or spec.get('original_name')
    sheet=str(spec.get('sheet',0))
    scoped={}
    # New UI keys are source|sheet|column. Legacy flat keys remain supported.
    for key,val in privacy_decisions.items():
        parts=str(key).split('|',2)
        if len(parts)==3:
            src,sh,col=parts
            if source_label is not None and src==source_label and sh==sheet:
                scoped[col]=val
        else:
            scoped[str(key)]=val
    return scoped

def _identity_fields(privacy_decisions, source_specs):
    """Union used by the final privacy gate; execution uses per-source fields."""
    fields={}
    for spec in source_specs:
        local=_decisions_for_spec(privacy_decisions,spec)
        for col,decision in local.items():
            action=ACTION_MAP.get(decision,decision)
            if action=='pseudonymize':
                fields[col]={'class':'identity','action':'pseudonymize','namespace':f'ui_{col}','prefix':'ID_','target_column':f'{col}_ID'}
            elif action in {'remove','keep','transformation_only'}:
                fields[col]={'class':'identity','action':action}
        case=spec.get('case_column')
        if case and case!='— select —':
            fields[case]={'class':'case','action':'pseudonymize','namespace':'case','prefix':'P','target_column':'Case_ID'}
    return fields

def _fields_for_spec(privacy_decisions, spec):
    local=_decisions_for_spec(privacy_decisions,spec)
    fields={}
    for col,decision in local.items():
        action=ACTION_MAP.get(decision,decision)
        if action=='pseudonymize':
            fields[col]={'class':'identity','action':'pseudonymize','namespace':f'ui_{col}','prefix':'ID_','target_column':f'{col}_ID'}
        elif action in {'remove','keep','transformation_only'}:
            fields[col]={'class':'identity','action':action}
    case=spec.get('case_column')
    if case and case!='— select —':
        fields[case]={'class':'case','action':'pseudonymize','namespace':'case','prefix':'P','target_column':'Case_ID'}
    return fields

def build_ui_config(project_name, source_specs, privacy_decisions, output_dir, vault_dir, temporal_constraints=None, identity_continuity=None):
    sources=[]
    all_identity_fields={}
    for spec in source_specs:
        local_decisions=_decisions_for_spec(privacy_decisions,spec)
        source_identity_fields=_fields_for_spec(privacy_decisions,spec)
        all_identity_fields.update(source_identity_fields)
        rules=[]
        for n,rule in enumerate(spec.get('event_rules',[]),1):
            case_col=spec.get('case_column')
            attrs=[_rewrite_after_privacy(a,local_decisions,case_col) for a in rule.get('attributes',[])]
            r={'name':rule.get('name') or f"{spec['name']}_event_{n}",'timestamp_from':_rewrite_after_privacy(rule['timestamp_from'],local_decisions,case_col),'attributes':attrs}
            if rule.get('activity_mode')=='constant':
                r['activity_value']=rule.get('activity_value','')
            else:
                r['activity_from']=_rewrite_after_privacy(rule.get('activity_from') or spec.get('activity_column'),local_decisions,case_col)
            if rule.get('activity_prefix'): r['activity_prefix']=rule['activity_prefix']
            if rule.get('activity_suffix'): r['activity_suffix']=rule['activity_suffix']
            if rule.get('where'):
                r['where']={_rewrite_after_privacy(k,local_decisions,case_col):v for k,v in rule['where'].items()}
            rules.append(r)
        if not rules:
            for n,ts in enumerate(spec.get('timestamps',[]),1):
                rules.append({'name':f"{spec['name']}_event_{n}",'timestamp_from':ts,'activity_from':spec['activity_column'],'attributes':spec.get('attributes',[])})
        source_cfg={'name':spec['name'],'path':str(Path(spec['path']).resolve()),'sheet':spec.get('sheet',0),
                    'event_rules':rules,'identity_fields':source_identity_fields,
                    'multiplicity_rules':[dict(x) for x in spec.get('multiplicity_rules',[])]}
        if spec.get('mapping'):
            m=dict(spec['mapping'])
            m['path']=str(Path(m['path']).resolve())
            m['source_keys']=[_rewrite_after_privacy(k,local_decisions,spec.get('case_column')) for k in m.get('source_keys',m.get('keys',[]))]
            source_cfg['mapping']=m
        sources.append(source_cfg)
    return {'project':{'name':project_name,'version':'1.4.0-ui'},
            'paths':{'identity_vault':str(Path(vault_dir).resolve()),'output':str(Path(output_dir).resolve())},
            'privacy':{'review_required_for_all_columns':False,'identity_fields':all_identity_fields},
            'sources':sources,
            'integration':{'duplicate_policy':'flag','temporal_constraints':temporal_constraints or []},'identity_continuity':identity_continuity or {}}

def save_ui_project(project_name, plugin_choice, source_specs, privacy_decisions):
    payload={'format':'processflow-ui-project','version':'1.0.1','project_name':project_name,'plugin_choice':plugin_choice,'privacy_decisions':privacy_decisions,'source_specs':source_specs}
    # paths are intentionally omitted: uploads must be reattached on another machine/session.
    for s in payload['source_specs']:
        s.pop('path',None)
        if s.get('mapping'): s['mapping'].pop('path',None)
    return json.dumps(payload,indent=2,default=str).encode()

def load_ui_project(data):
    obj=json.loads(data.decode() if isinstance(data,(bytes,bytearray)) else data)
    if obj.get('format')!='processflow-ui-project': raise ValueError('Not a compatible UI project file')
    return obj

def _package(output,run_root):
    package=Path(run_root)/'result_package.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in Path(output).rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(output))
    return package


def _lookup_manifest(vault):
    vault=Path(vault)
    files=[]
    total=0
    for p in sorted(vault.glob('*_lookup.csv')):
        try:
            df=pd.read_csv(p)
            rows=len(df)
        except (pd.errors.EmptyDataError, FileNotFoundError):
            rows=0
        total += rows
        files.append({'file':p.name,'rows':rows})
    return {
        'classification':'RESTRICTED - RE-IDENTIFICATION MATERIAL',
        'warning':'Contains original identifiers and pseudonyms. Do not distribute with de-identified results unless specifically authorized.',
        'lookup_files':files,
        'identity_rows':total
    }

def _restricted_package(output, vault, run_root):
    package=Path(run_root)/'complete_run_RESTRICTED.zip'
    manifest=_lookup_manifest(vault)
    manifest_path=Path(run_root)/'Lookup_Manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    warning_path=Path(run_root)/'RESTRICTED_LOOKUPS_WARNING.txt'
    warning_path.write_text(
        'RESTRICTED - CONTAINS RE-IDENTIFICATION LOOKUP TABLES\\n'
        'Do not distribute this folder with de-identified process-mining results unless specifically authorized by organizational data-governance.\\n',
        encoding='utf-8')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in Path(output).rglob('*'):
            if p.is_file(): z.write(p,Path('01_SAFE_RESULTS')/p.relative_to(output))
        for p in Path(vault).glob('*_lookup.csv'):
            if p.is_file(): z.write(p,Path('02_RESTRICTED_LOOKUPS')/p.name)
        z.write(manifest_path,Path('02_RESTRICTED_LOOKUPS')/'Lookup_Manifest.json')
        z.write(warning_path,Path('02_RESTRICTED_LOOKUPS')/'README_RESTRICTED.txt')
    return package,manifest

def _load_baseline_event_log(path, column_map=None):
    path=Path(path)
    df=pd.read_csv(path) if path.suffix.lower()=='.csv' else pd.read_excel(path)
    df=df.copy()
    column_map=column_map or {}
    semantic={'Case_ID':column_map.get('case_id','Case_ID'),'Activity':column_map.get('activity','Activity'),'Timestamp':column_map.get('timestamp','Timestamp')}
    missing=[source for source in semantic.values() if source not in df.columns]
    if missing: raise ValueError(f"Existing event log is missing selected column(s): {', '.join(map(str,missing))}")
    selected=list(semantic.values())
    if len(set(selected))!=3: raise ValueError('Case identifier, Activity, and Timestamp must be three different columns.')
    rename={source:canonical for canonical,source in semantic.items() if source!=canonical}
    collisions=[canonical for canonical,source in semantic.items() if canonical in df.columns and source!=canonical and canonical not in selected]
    if collisions: raise ValueError('Cannot standardize event log because canonical column(s) already exist: '+', '.join(collisions))
    df=df.rename(columns=rename)
    df['Timestamp']=pd.to_datetime(df['Timestamp'],errors='coerce')
    if df['Timestamp'].isna().any():
        raise ValueError('Existing event log contains missing/unparseable Timestamp values')
    if 'Source' not in df.columns: df['Source']='Existing Event Log'
    return df

def run_ui_project(project_name, source_specs, privacy_decisions, run_root, temporal_constraints=None,
                   case_lookup=None, population_mode='allow_new', baseline_event_log=None, baseline_column_map=None):
    run_root=Path(run_root); run_root.mkdir(parents=True,exist_ok=True); output=run_root/'output'; vault=run_root/'secure_local'
    identity_cfg={'population_mode':population_mode}
    if case_lookup:
        identity_cfg['case_lookup']=str(Path(case_lookup).resolve())
    cfg=build_ui_config(project_name,source_specs,privacy_decisions,output,vault,
                        temporal_constraints=temporal_constraints,identity_continuity=identity_cfg)
    baseline=None
    if baseline_event_log:
        baseline=_load_baseline_event_log(baseline_event_log,baseline_column_map)
        anchor_path=run_root/'baseline_anchor_context.csv'
        baseline.to_csv(anchor_path,index=False)
        cfg.setdefault('integration',{})['multiplicity_anchor_event_log']=str(anchor_path.resolve())
    config_path=run_root/'ui_generated_project.yaml'; config_path.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    result=run_project(config_path)

    # Attach stable UI-facing source identity to post-run discovery tables.
    # This avoids brittle matching between generated internal source names and uploaded filenames.
    internal_to_ui={str(spec.get('name')):str(spec.get('ui_source_name') or spec.get('name')) for spec in source_specs}
    for key in ('repeated_activity_occurrences','repeated_activity_occurrences_after_resolution','multiplicity_resolution_audit'):
        table=result.get(key)
        if isinstance(table,pd.DataFrame) and not table.empty and 'Source' in table.columns:
            table=table.copy()
            table['UI_Source']=table['Source'].astype(str).map(internal_to_ui)
            result[key]=table

    if baseline_event_log:
        new=pd.read_csv(result['paths']['event_log'])
        new['Timestamp']=pd.to_datetime(new['Timestamp'],errors='coerce')
        baseline_events=len(baseline); new_events=len(new)
        signature_cols=['Case_ID','Activity','Timestamp','Source']
        # Baseline is immutable. Duplicate signatures already present there are QA only.
        baseline_dup_mask=baseline.duplicated(subset=signature_cols,keep=False)
        baseline_duplicate_rows=int(baseline_dup_mask.sum())
        baseline_duplicate_signatures=int(baseline.loc[baseline_dup_mask,signature_cols].drop_duplicates().shape[0])

        # Repeated incoming signatures are QA/discovery only. Detection never implies deletion.
        new_dup_all_mask=new.duplicated(subset=signature_cols,keep=False)
        duplicate_inspection=new.loc[new_dup_all_mask].copy()
        if not duplicate_inspection.empty:
            group_keys=duplicate_inspection[signature_cols].astype(str).agg('||'.join,axis=1)
            codes,_=pd.factorize(group_keys,sort=False)
            duplicate_inspection.insert(0,'Repeated_Signature_Group',[f'REP_{i+1:04d}' for i in codes])
            duplicate_inspection.insert(1,'Group_Size', duplicate_inspection.groupby('Repeated_Signature_Group')['Repeated_Signature_Group'].transform('size'))
            duplicate_inspection=duplicate_inspection.sort_values(['Repeated_Signature_Group','Case_ID','Timestamp','Activity'],kind='stable')
        incoming_duplicates=int(new.duplicated(subset=signature_cols,keep='first').sum())
        incoming_duplicate_groups=int(new.loc[new_dup_all_mask,signature_cols].drop_duplicates().shape[0])
        incoming_duplicate_rows_for_inspection=int(new_dup_all_mask.sum())
        # Preserve every generated incoming occurrence. Activity-specific multiplicity rules, when enabled,
        # have already been applied upstream and are the only within-batch exclusion mechanism.
        new_unique_batch=new.copy()

        # Only incoming events are tested against the established baseline.
        baseline_keys=set(map(tuple,baseline[signature_cols].itertuples(index=False,name=None)))
        incoming_keys=list(map(tuple,new_unique_batch[signature_cols].itertuples(index=False,name=None)))
        overlap_mask=pd.Series([k in baseline_keys for k in incoming_keys],index=new_unique_batch.index)
        incoming_already_in_baseline=int(overlap_mask.sum())
        to_append=new_unique_batch.loc[~overlap_mask].copy()
        new_unique_events_added=len(to_append)

        # Preserve every baseline row; append only genuinely new incoming rows.
        combined=pd.concat([baseline,to_append],ignore_index=True,sort=False)
        combined=combined.sort_values(['Case_ID','Timestamp','Activity'],kind='stable').reset_index(drop=True)
        combined.to_csv(result['paths']['event_log'],index=False)

        analysis_tables=build_process_analysis(combined)
        analysis_dir=Path(output)/'analysis'; analysis_dir.mkdir(exist_ok=True)
        for name,table in analysis_tables.items(): table.to_csv(analysis_dir/f'{name}.csv',index=False)
        duplicate_report_path=analysis_dir/'incoming_duplicate_inspection.csv'
        duplicate_inspection.to_csv(duplicate_report_path,index=False)
        inc=pd.DataFrame([{'baseline_events':baseline_events,'new_generated_events':new_events,
                           'baseline_duplicate_rows_qa_only':baseline_duplicate_rows,
                           'baseline_duplicate_signatures_qa_only':baseline_duplicate_signatures,
                           'incoming_duplicates_within_batch':incoming_duplicates,
                           'incoming_duplicate_groups':incoming_duplicate_groups,
                           'incoming_duplicate_rows_for_inspection':incoming_duplicate_rows_for_inspection,
                           'incoming_events_already_in_baseline':incoming_already_in_baseline,
                           'new_unique_events_added':new_unique_events_added,
                           'incoming_repeated_signatures_qa_only':incoming_duplicates,
                           'final_events':len(combined),
                           'final_cases':combined['Case_ID'].nunique()}])
        inc.to_csv(Path(output)/'qa_incremental_integration.csv',index=False)
        result['incremental_integration']=inc.iloc[0].to_dict()
        # Re-evaluate the gate against the actual combined event log and prove baseline + added = final.
        result['quality_gate']=augment_incremental_quality(result['quality_gate'],combined,result['incremental_integration'])
        result['summary']['quality_status']=result['quality_gate']['status']
        qdir=Path(result['paths']['qa_dir'])
        result['quality_gate']['checks'].to_csv(qdir/'quality_checks.csv',index=False)
        source_recon=result.get('source_reconciliation',pd.DataFrame())
        def _read_qa(path):
            try: return pd.read_csv(path) if path.exists() else pd.DataFrame()
            except pd.errors.EmptyDataError: return pd.DataFrame()
        rule_diag=_read_qa(qdir/'event_rule_diagnostics.csv')
        map_diag=_read_qa(qdir/'mapping_diagnostics.csv')
        mult=result.get('multiplicity_resolution_audit',pd.DataFrame())
        temporal=_read_qa(qdir/'temporal_violations.csv')
        validation_zip,validation_dir=write_validation_package(output,result['quality_gate'],source_recon,rule_diag,map_diag,mult,temporal)
        result['paths']['validation_report']=validation_zip; result['paths']['validation_dir']=validation_dir
        result['duplicate_inspection']=duplicate_inspection
        result['duplicate_inspection_path']=str(duplicate_report_path)
        result['summary']=event_log_summary(combined)
        result['available_activities']=sorted(combined['Activity'].dropna().astype(str).unique().tolist())

    result['package']=str(_package(output,run_root))
    restricted,vault_manifest=_restricted_package(output,vault,run_root)
    result['restricted_package']=str(restricted)
    result['vault_summary']={'lookup_files':len(vault_manifest['lookup_files']),'identity_rows':vault_manifest['identity_rows']}
    result['generated_config']=str(config_path)
    return result

