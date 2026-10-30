from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import tempfile, uuid, json
import pandas as pd
import streamlit as st
import json
from pipeline.ingestion import inspect_excel, load_excel_source
from pipeline.privacy import scan_columns
from pipeline.ui_bridge import run_ui_project,save_ui_project,load_ui_project
from pipeline.mapping import apply_mapping
from pipeline.analysis import build_process_analysis, analysis_csv_package
from pipeline.identity_vault import LocalIdentityVault

st.set_page_config(page_title='ProcessFlow — Event Log Engineering',layout='wide')
def init():
    defaults={'sources':{},'source_types':{},'event_log_column_maps':{},'privacy_decisions':{},'source_configs':{},'project_name':'New Process Mining Project','run_result':None,'loaded_project':None,'multiplicity_discovery':[],'post_run_notice':None,'quality_exception_approvals':{},'quality_run_token':None}
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k]=v
init()

@st.cache_data(show_spinner=False)
def cached_load_table(path, sheet):
    p=Path(path)
    if p.suffix.lower()=='.csv':
        return pd.read_csv(p)
    return load_excel_source(p,sheet)

st.title('ProcessFlow — Event Log Engineering'); st.caption('Human-configured • machine-executed • privacy-gated • auditable')
if st.session_state.get('post_run_notice'):
    st.info(st.session_state.post_run_notice)
    st.session_state.post_run_notice=None
with st.sidebar:
    st.header('Project'); st.session_state.project_name=st.text_input('Project name',st.session_state.project_name)
    plugin_choice='Generic / configuration only'
    project_file=st.file_uploader('Load saved project configuration',type=['json'],key='project_load')
    if project_file and st.button('Apply saved configuration'):
        try:
            obj=load_ui_project(project_file.getvalue()); st.session_state.project_name=obj['project_name']; st.session_state.privacy_decisions=obj.get('privacy_decisions',{}); st.session_state.loaded_project=obj
            st.success('Configuration loaded. Reattach the source/mapping files, then review before running.')
        except Exception as e: st.error(str(e))
    specs=list(st.session_state.source_configs.values())
    st.download_button('Save project configuration',save_ui_project(st.session_state.project_name,plugin_choice,specs,dict(st.session_state.privacy_decisions)),file_name='ProcessFlow_Project_Config.json',mime='application/json')

tabs=st.tabs(['1 · Sources','2 · Privacy','3 · Events & mappings','4 · Validate & run','5 · Results','6 · Analysis'])
with tabs[0]:
    st.subheader('Register data sources')
    st.caption('Classify each upload as raw source data or an existing standardized event log. Event logs bypass raw event-definition screens.')
    files=st.file_uploader('Excel / CSV inputs',type=['xlsx','xlsm','csv'],accept_multiple_files=True,key='source_uploads')

    uploaded_names={f.name for f in (files or [])}
    # Streamlit's uploader can remove a file without rerunning our old cleanup path.
    # Purge all source-specific state as soon as it is no longer present in the uploader.
    stale=set(st.session_state.sources)-uploaded_names
    for stale_name in stale:
        st.session_state.sources.pop(stale_name,None)
        st.session_state.source_types.pop(stale_name,None)
        st.session_state.event_log_column_maps.pop(stale_name,None)
        st.session_state.source_configs.pop(stale_name,None)
        for k in list(st.session_state.privacy_decisions):
            if str(k).startswith(f'{stale_name}|'): st.session_state.privacy_decisions.pop(k,None)
        for k in list(st.session_state.keys()):
            if stale_name in str(k) and k not in {'sources','source_types','source_configs','privacy_decisions'}:
                try: del st.session_state[k]
                except Exception: pass

    for f in files or []:
        if f.name not in st.session_state.sources:
            path=Path(tempfile.gettempdir())/f"processflow_{uuid.uuid4().hex}_{f.name}"; path.write_bytes(f.getvalue())
            try:
                meta=inspect_excel(path) if path.suffix.lower()!='.csv' else {'CSV':{'rows':len(pd.read_csv(path)),'columns':list(pd.read_csv(path,nrows=1).columns)}}
                st.session_state.sources[f.name]={'path':str(path),'meta':meta}
                st.session_state.source_types.setdefault(f.name,'Raw source data')
            except Exception as e: st.error(f'{f.name}: {e}')

    for name,item in list(st.session_state.sources.items()):
        with st.expander(name,expanded=True):
            current=st.session_state.source_types.get(name,'Raw source data')
            input_type=st.radio('Input type',['Raw source data','Existing standardized event log'],
                                index=0 if current=='Raw source data' else 1,
                                horizontal=True,key=f'input_type_{name}')
            st.session_state.source_types[name]=input_type
            if input_type=='Existing standardized event log':
                # Event logs are already standardized: never retain or validate raw event rules.
                st.session_state.source_configs.pop(name,None)
                for k in list(st.session_state.privacy_decisions):
                    if str(k).startswith(f'{name}|'):
                        st.session_state.privacy_decisions.pop(k,None)
            sheet=st.selectbox('Preview sheet',list(item['meta']),key=f'preview_{name}')
            df=cached_load_table(item['path'],sheet)
            st.dataframe(df.head(20),use_container_width=True); st.caption(f'{len(df):,} rows × {len(df.columns):,} columns')
            if input_type=='Existing standardized event log':
                cols=list(df.columns)
                def guess(options):
                    normalized={str(c).strip().lower():c for c in cols}
                    for candidate in options:
                        if candidate.lower() in normalized: return normalized[candidate.lower()]
                    return None
                guessed_case=guess(['Case_ID','case_id','case id','caseid'])
                guessed_activity=guess(['Activity','activity','event','event_name','event name'])
                guessed_timestamp=guess(['Timestamp','timestamp','event_time','event time','datetime','date_time'])
                st.markdown('**Event-log column roles**')
                st.caption('Confirm the three required process-mining fields. Other columns are preserved as attributes.')
                blank=['— select —']; c1,c2,c3=st.columns(3)
                case_col=c1.selectbox('Case identifier',blank+cols,index=(cols.index(guessed_case)+1) if guessed_case in cols else 0,key=f'elog_case_{name}')
                activity_col=c2.selectbox('Activity',blank+cols,index=(cols.index(guessed_activity)+1) if guessed_activity in cols else 0,key=f'elog_activity_{name}')
                timestamp_col=c3.selectbox('Timestamp',blank+cols,index=(cols.index(guessed_timestamp)+1) if guessed_timestamp in cols else 0,key=f'elog_timestamp_{name}')
                selected=[case_col,activity_col,timestamp_col]
                if '— select —' in selected:
                    st.error('Select the Case identifier, Activity, and Timestamp columns.')
                    st.session_state.event_log_column_maps.pop(name,None)
                elif len(set(selected))<3:
                    st.error('Case identifier, Activity, and Timestamp must be different columns.')
                    st.session_state.event_log_column_maps.pop(name,None)
                else:
                    st.session_state.event_log_column_maps[name]={'case_id':case_col,'activity':activity_col,'timestamp':timestamp_col}
                    st.success(f'Event log ready: {case_col} → Case_ID · {activity_col} → Activity · {timestamp_col} → Timestamp')

    raw_sources={n:i for n,i in st.session_state.sources.items() if st.session_state.source_types.get(n,'Raw source data')=='Raw source data'}
    event_log_sources={n:i for n,i in st.session_state.sources.items() if st.session_state.source_types.get(n)=='Existing standardized event log'}

with tabs[1]:
    st.subheader('Privacy review')
    st.caption('Check only columns that require privacy handling. Unchecked columns are kept unchanged as analytical attributes.')
    st.info('Likely direct identifiers may be pre-checked as a recommendation. You can check or uncheck any column before continuing.')

    privacy_choices=['Pseudonymize','Remove']
    for name,item in raw_sources.items():
        sheet=st.selectbox(f'{name} sheet',list(item['meta']),key=f'privsheet_{name}')
        df=cached_load_table(item['path'],sheet)
        findings=scan_columns(df.columns)
        detected_cols={x['column'] for x in findings}

        st.markdown(f'**{name} — {sheet}**')
        st.caption('☑ Privacy handling enabled · ☐ Keep unchanged')

        for col in df.columns:
            key=f'{name}|{sheet}|{col}'
            col_l=str(col).strip().lower()

            # Conservative auto-selection: only obvious identity/personnel fields.
            obvious_identifier = (
                col_l in {'customer id','customer name','customer_name','username','staff name','staff_name',
                          'rad onc','rad_onc','med onc','med_onc','completed by','assigned by'}
                or 'customer id' in col_l
                or 'customer name' in col_l
                or 'staff name' in col_l
                or 'username' in col_l
                or 'physician name' in col_l
                or 'provider name' in col_l
            )
            default_checked = obvious_identifier and col in detected_cols

            existing=st.session_state.privacy_decisions.get(key)
            if existing in ('Pseudonymize','Remove'):
                default_checked=True

            c1,c2,c3=st.columns([0.6,2.2,3.2])
            enabled=c1.checkbox('Handle',value=default_checked,key=f'privacy_enabled_{key}',label_visibility='collapsed')
            c2.markdown(f'**{col}**')

            if enabled:
                default_action=existing if existing in privacy_choices else ('Remove' if 'customer name' in col_l else 'Pseudonymize')
                action=c3.selectbox('Privacy action',privacy_choices,index=privacy_choices.index(default_action),
                                    key=f'privacy_action_{key}',label_visibility='collapsed')
                st.session_state.privacy_decisions[key]=action
            else:
                c3.caption('Keep unchanged')
                st.session_state.privacy_decisions[key]='Keep'

with tabs[2]:
    st.subheader('Events & mappings')
    if plugin_choice=='Generic / configuration only':
        st.write('Define one or more event rules per source. Mappings run before event rules, so mapped output columns can be used for filters and activities.')
        for name,item in raw_sources.items():
            with st.expander(name,expanded=True):
                sheet=st.selectbox('Event sheet',list(item['meta']),key=f'evsheet_{name}')
                df=cached_load_table(item['path'],sheet)
                cols=list(df.columns); blank=['— select —']
                case=st.selectbox('Case identifier → Case_ID',blank+cols,key=f'case_{name}')
                attrs=st.multiselect('Default attributes to preserve',[c for c in cols if c!=case],key=f'attrs_{name}')

                mapping_cfg=None; mapped_outputs=[]
                mf=st.file_uploader('Optional external mapping',type=['xlsx','csv'],key=f'map_{name}')
                if mf:
                    mp=Path(tempfile.gettempdir())/f"processflow_map_{uuid.uuid4().hex}_{mf.name}"; mp.write_bytes(mf.getvalue())
                    mdf=cached_load_table(str(mp),0)
                    st.markdown('**Mapping key column(s)**')
                    pair_count=st.number_input('Number of mapping key pairs',1,6,1,key=f'mpairn_{name}')
                    source_keys=[]; mapping_keys=[]
                    for j in range(int(pair_count)):
                        c1,c2=st.columns(2)
                        sk=c1.selectbox(f'Source key {j+1}',blank+cols,key=f'mskey_{name}_{j}')
                        mk=c2.selectbox(f'Mapping-file key {j+1}',blank+list(mdf.columns),key=f'mmkey_{name}_{j}')
                        if sk!='— select —' and mk!='— select —': source_keys.append(sk); mapping_keys.append(mk)
                    outputs=st.multiselect('Mapping output column(s)',[c for c in mdf.columns if c not in mapping_keys],key=f'mouts_{name}')
                    policy=st.selectbox('Unmapped policy',['keep','drop','error'],index=1,key=f'mpol_{name}',help='drop excludes unmapped rows but records them in the unmapped report; error blocks the run.')
                    if len(source_keys)==int(pair_count) and len(mapping_keys)==int(pair_count) and outputs:
                        st.markdown('**How should mapped outputs affect event creation?**')
                        activity_output=st.selectbox('Mapped output to use as Activity (optional)',['— none —']+outputs,key=f'mactivity_{name}',
                                                     help='When selected, this mapped column replaces the raw activity field for non-constant event rules.')
                        include_column=st.selectbox('Mapped output used to include/exclude rows (optional)',['— none —']+outputs,key=f'minclude_{name}',
                                                   help='Use this when the mapping contains a field such as Keep for PM?.')
                        include_values=[]
                        if include_column!='— none —':
                            vals=sorted(mdf[include_column].dropna().astype(str).unique().tolist())
                            include_values=st.multiselect('Value(s) that should CREATE events',vals,key=f'mincludevals_{name}')
                        mapping_cfg={'path':str(mp),'sheet':0,'source_keys':source_keys,'mapping_keys':mapping_keys,'outputs':outputs,
                                     'unmapped_policy':policy,
                                     'activity_output':None if activity_output=='— none —' else activity_output,
                                     'include_column':None if include_column=='— none —' else include_column,
                                     'include_values':include_values}
                        mapped_outputs=list(outputs)
                        try:
                            _,preview_diag=apply_mapping(df,mdf,source_keys=source_keys,mapping_keys=mapping_keys,outputs=outputs,unmapped_policy='keep')
                            pc1,pc2,pc3=st.columns(3)
                            pc1.metric('Mapping coverage',f"{preview_diag['coverage']*100:.1f}%")
                            pc2.metric('Mapped rows',preview_diag['rows_mapped'])
                            pc3.metric('Unmapped rows',preview_diag['rows_unmapped'])
                            if preview_diag['rows_unmapped']:
                                st.warning('Some source rows are unmapped. Review the preview below before running.')
                                st.dataframe(preview_diag['unmapped_keys'].head(100),use_container_width=True)
                            else:
                                st.success('Mapping preview: all source rows matched a mapping key.')
                        except Exception as e:
                            st.error(f'Mapping preview failed: {e}')
                    st.dataframe(mdf.head(20),use_container_width=True)

                available=cols+[c for c in mapped_outputs if c not in cols]
                st.caption('Mapped output columns appear below because mapping is applied before event generation.')
                n=st.number_input('Number of event rules',1,12,1,key=f'nrules_{name}'); rules=[]
                for i in range(int(n)):
                    st.markdown(f'**Event rule {i+1}**')
                    ts=st.selectbox('Timestamp field',blank+available,key=f'rts_{name}_{i}')
                    mode=st.radio('Activity definition',['From field','Constant label'],horizontal=True,key=f'rmode_{name}_{i}')
                    if mode=='From field':
                        af=st.selectbox('Activity field',blank+available,key=f'raf_{name}_{i}'); av=''
                        c1,c2=st.columns(2); prefix=c1.text_input('Optional activity prefix',key=f'rpre_{name}_{i}'); suffix=c2.text_input('Optional activity suffix',key=f'rsuf_{name}_{i}',placeholder=' e.g.  Assigned')
                    else:
                        af=None; av=st.text_input('Activity label',key=f'rav_{name}_{i}'); prefix=suffix=''
                    use_filter=st.checkbox('Filter rows for this event rule',key=f'rfilter_{name}_{i}')
                    where={}
                    if use_filter:
                        fc=st.selectbox('Filter column',blank+available,key=f'rfcol_{name}_{i}')
                        fv=st.text_input('Allowed value',key=f'rfval_{name}_{i}',placeholder='YES')
                        if fc!='— select —' and fv!='': where={fc:fv}
                    rules.append({'name':f'{Path(name).stem}_event_{i+1}','timestamp_from':None if ts=='— select —' else ts,'activity_mode':'constant' if mode=='Constant label' else 'field','activity_from':None if af=='— select —' else af,'activity_value':av,'activity_prefix':prefix,'activity_suffix':suffix,'attributes':attrs,'where':where})

                # Preserve any analyst-configured multiplicity rules. The visible
                # post-run resolution panel is rendered after all source event rules.
                source_internal=Path(name).stem.replace(' ','_')
                multiplicity_rules=st.session_state.source_configs.get(name,{}).get('multiplicity_rules',[])
                st.session_state.source_configs[name]={'name':source_internal,'ui_source_name':name,'path':item['path'],'sheet':sheet,'case_column':case,'attributes':attrs,'event_rules':rules,'mapping':mapping_cfg,'multiplicity_rules':multiplicity_rules}

        # Post-run discovery -> configuration loop.
        prior=st.session_state.get('run_result') or {}
        registry=st.session_state.get('multiplicity_discovery',[])
        discovered=pd.DataFrame(registry) if registry else prior.get('repeated_activity_occurrences')
        if not registry and not (isinstance(discovered,pd.DataFrame) and not discovered.empty):
            st.caption('Repeated-activity configuration: no discovery trigger is currently stored. Run the pipeline once to populate it.')
        if isinstance(discovered,pd.DataFrame) and not discovered.empty:
            st.markdown('---')
            st.subheader('⚠ Configure repeated activity occurrences')
            st.caption(f"Triggered by the last successful run: {len(discovered):,} affected source/activity combinations detected.")
            st.info(
                'The last run found activities that occur more than once for at least one Case_ID. '
                'Nothing is removed automatically. Inspect the findings in Results, then configure '
                'only the activities for which your process definition requires one occurrence per case.'
            )
            strategy_labels={
                'Earliest occurrence':'earliest',
                'Latest occurrence':'latest',
                'Closest before another activity':'closest_before_anchor',
                'Closest after another activity':'closest_after_anchor',
                'Closest to another activity':'closest_to_anchor',
                'First source record':'first_source_record',
                'Last source record':'last_source_record'
            }
            reverse={v:k for k,v in strategy_labels.items()}
            all_activities=prior.get('available_activities') or sorted(discovered['Activity'].dropna().astype(str).unique().tolist())

            # Discovery now carries the exact uploaded-source UI identity from the run.
            # Fall back to internal-name matching only for results created by older versions.
            config_by_internal={str(cfg.get('name')):ui_name for ui_name,cfg in st.session_state.source_configs.items()}
            group_col='UI_Source' if 'UI_Source' in discovered.columns and discovered['UI_Source'].notna().any() else 'Source'
            for source_value,grp in discovered.groupby(group_col,dropna=False,sort=False):
                if group_col=='UI_Source':
                    ui_name=str(source_value)
                    internal=str(grp['Source'].iloc[0])
                else:
                    internal=str(source_value)
                    ui_name=config_by_internal.get(internal)
                if ui_name not in st.session_state.source_configs:
                    st.warning(
                        f'Repeated activities were detected for source {internal}, but the uploaded raw source could not be matched '
                        'to its editable configuration. Reattach that raw source and rerun.'
                    )
                    continue
                cfg=st.session_state.source_configs[ui_name]
                existing={str(x.get('activity')):dict(x) for x in cfg.get('multiplicity_rules',[])}
                st.markdown(f'**Source: {ui_name}**')
                for _,row in grp.sort_values('Activity').iterrows():
                    activity=str(row['Activity'])
                    old=existing.get(activity,{})
                    cases=int(row['cases_with_multiple_occurrences'])
                    extra=int(row['additional_occurrences'])
                    with st.expander(f'{activity} — {cases:,} affected cases · {extra:,} additional occurrences', expanded=False):
                        enabled=st.checkbox(
                            'Handle multiple occurrences for this activity',
                            value=bool(old.get('enabled',False)),
                            key=f'resolve_enable_{internal}_{activity}'
                        )
                        rule={'source':internal,'activity':activity,'enabled':enabled,'action':'keep_one' if enabled else 'keep_all'}
                        if enabled:
                            labels=list(strategy_labels)
                            old_label=reverse.get(old.get('strategy'),'Earliest occurrence')
                            label=st.selectbox(
                                'Selection rule',
                                labels,
                                index=labels.index(old_label),
                                key=f'resolve_strategy_{internal}_{activity}'
                            )
                            rule['strategy']=strategy_labels[label]
                            if rule['strategy'] in {'closest_before_anchor','closest_after_anchor','closest_to_anchor'}:
                                anchors=[a for a in all_activities if a!=activity]
                                if anchors:
                                    old_anchor=old.get('anchor_activity')
                                    ai=anchors.index(old_anchor) if old_anchor in anchors else 0
                                    rule['anchor_activity']=st.selectbox(
                                        'Reference activity',
                                        anchors,index=ai,
                                        key=f'resolve_anchor_{internal}_{activity}'
                                    )
                                    rule['anchor_occurrence']=st.radio(
                                        'Reference occurrence',
                                        ['first','last'],
                                        index=1 if old.get('anchor_occurrence')=='last' else 0,
                                        horizontal=True,
                                        key=f'resolve_anchor_occ_{internal}_{activity}'
                                    )
                                else:
                                    st.error('No other activity is available as an anchor.')
                            st.caption('This rule is applied only to this activity. Rerun the pipeline to apply it; exclusions will appear in the multiplicity-resolution audit.')
                        else:
                            st.caption('Keep all occurrences. This activity remains discovery/QA only.')
                        existing[activity]=rule
                cfg['multiplicity_rules']=list(existing.values())
                st.session_state.source_configs[ui_name]=cfg
            st.success('After changing a rule, go to **Validate & run** and run the pipeline again.')

with tabs[3]:
    # Session-state invariant: only currently registered RAW sources may have event configs.
    active_raw=set(raw_sources)
    for configured_name in list(st.session_state.source_configs):
        if configured_name not in active_raw:
            st.session_state.source_configs.pop(configured_name,None)

    st.subheader('Validation & execution gate'); # Compatibility/safety invariant: v=="UNRESOLVED" blocks execution.
    unresolved=[k for k,v in st.session_state.privacy_decisions.items() if v=='UNRESOLVED']
    if unresolved: st.error('Execution/export is blocked while privacy findings remain unresolved.')
    if plugin_choice=='Generic / configuration only':
        bad=[]
        for name in raw_sources:
            spec=st.session_state.source_configs.get(name)
            if not spec:
                bad.append(name)
                continue
            rules=spec.get('event_rules',[])
            if spec.get('case_column')=='— select —' or not rules or any(not r.get('timestamp_from') or (r.get('activity_mode')=='constant' and not r.get('activity_value')) or (r.get('activity_mode')=='field' and not r.get('activity_from')) or (r.get('where') is not None and any(not k or v=='' for k,v in r.get('where',{}).items())) for r in rules): bad.append(name)
        ready=bool(raw_sources) and not unresolved and not bad and all(name in st.session_state.source_configs for name in raw_sources)
        if bad: st.error('Incomplete event rules for: '+', '.join(bad))

    if ready: st.success('Preflight passed. Project is ready to execute.')
    temporal_constraints=[]
    if plugin_choice=='Generic / configuration only':
        st.markdown('**Optional temporal-order constraints**')
        st.caption('Define business-approved ordering rules. Same-day date-only ambiguity may be adjusted and audited; cross-date violations are reported, not rewritten.')
        n_tc=st.number_input('Number of temporal constraints',min_value=0,max_value=10,value=0,step=1,key='n_temporal_constraints')
        for j in range(int(n_tc)):
            c1,c2=st.columns(2)
            before=c1.text_input(f'Constraint {j+1}: activity that must occur first',key=f'tc_before_{j}')
            after=c2.text_input(f'Constraint {j+1}: activity that must occur after',key=f'tc_after_{j}')
            if before.strip() and after.strip():
                temporal_constraints.append({'before':before.strip(),'after':after.strip()})
    identity_mode='allow_new'
    case_lookup_path=None
    baseline_event_log_path=None
    baseline_column_map=None
    if plugin_choice=='Generic / configuration only' and event_log_sources:
        st.markdown('**Incremental integration**')
        if len(event_log_sources)>1:
            st.error('Only one existing standardized event log can be used as the baseline in this release.')
            ready=False
        else:
            baseline_name,baseline_item=next(iter(event_log_sources.items()))
            baseline_event_log_path=baseline_item['path']
            baseline_column_map=st.session_state.event_log_column_maps.get(baseline_name)
            if not baseline_column_map:
                st.error('Confirm the baseline event-log Case identifier, Activity, and Timestamp columns in Sources.')
                ready=False
            st.success(f'Baseline event log: {baseline_name}')
            st.caption('To safely link new raw identifiers to existing Case_IDs, provide the established identity lookup from the run that created this event log.')
            lookup_upload=st.file_uploader('Established identity lookup',type=['csv','xlsx','xlsm','xls'],key='case_lookup_upload',
                help='Accepted: CSV or Excel. Required columns: original_value and pseudonym. Header whitespace/BOM/case are normalized.')
            pop_label=st.radio('Incoming population handling',
                ['Existing cohort only — exclude unknown identifiers','Allow new cases — extend the identity lookup'],index=0,key='population_mode')
            identity_mode='existing_only' if pop_label.startswith('Existing cohort only') else 'allow_new'
            if lookup_upload:
                lookup_suffix=Path(lookup_upload.name).suffix.lower() or '.csv'
                case_lookup_path=str(Path(tempfile.gettempdir())/f'processflow_lookup_{uuid.uuid4().hex}{lookup_suffix}')
                Path(case_lookup_path).write_bytes(lookup_upload.getvalue())
                try:
                    lookup_preview=LocalIdentityVault.read_lookup_table(case_lookup_path)
                    st.success(f"Identity lookup validated: {len(lookup_preview):,} rows · recognized original_value → pseudonym.")
                    st.dataframe(lookup_preview[['original_value','pseudonym']].head(10),use_container_width=True)
                except Exception as e:
                    st.error(f'Identity lookup validation failed: {e}')
                    case_lookup_path=None
                    ready=False
            else:
                st.warning('The established identity lookup is required before incremental integration can run.')
                ready=False

    if st.button('Run Pipeline',type='primary',disabled=not ready):
        try:
            run_root=Path(tempfile.gettempdir())/f'processflow_run_{uuid.uuid4().hex}'
            if plugin_choice=='Generic / configuration only':
                # Preserve source/sheet scope. Columns with the same name in different sources
                # must not overwrite one another's privacy decisions.
                decisions=dict(st.session_state.privacy_decisions)
                st.session_state.run_result=run_ui_project(st.session_state.project_name,list(st.session_state.source_configs.values()),decisions,run_root,temporal_constraints=temporal_constraints,case_lookup=case_lookup_path,population_mode=identity_mode,baseline_event_log=baseline_event_log_path,baseline_column_map=baseline_column_map)
                _disc=st.session_state.run_result.get('repeated_activity_occurrences')
                st.session_state.multiplicity_discovery=_disc.to_dict('records') if isinstance(_disc,pd.DataFrame) else []
            _trigger_count=len(st.session_state.get('multiplicity_discovery',[]))
            # A new run requires a fresh exception review; approvals never carry silently across runs.
            _new_token=str(st.session_state.run_result.get('paths',{}).get('manifest',''))
            if st.session_state.get('quality_run_token') != _new_token:
                st.session_state.quality_exception_approvals={}
                st.session_state.quality_run_token=_new_token
            _qstatus=(st.session_state.run_result.get('quality_gate') or {}).get('status','NOT ASSESSED')
            st.session_state.post_run_notice=(
                f'Pipeline execution completed. Event Log Quality Gate: {_qstatus}. '
                f'{_trigger_count} repeated-activity configuration trigger(s) saved. '
                'The interface was refreshed so Events & mappings can display the new controls.'
            )
            # Critical Streamlit behavior: tab contents earlier in this script were rendered
            # before the Run button executed. Force a fresh script pass so Events & mappings
            # is rebuilt from the newly persisted discovery registry.
            st.rerun()
        except Exception as e: st.session_state.run_result={'error':str(e)}; st.error(f'Pipeline blocked/failed: {e}')

with tabs[4]:
    st.subheader('Results'); r=st.session_state.run_result
    if not r: st.info('No completed run yet.')
    elif 'error' in r: st.error(r['error'])
    else:
        s=r['summary']
        quality=r.get('quality_gate') or {}
        qstatus=quality.get('status','NOT ASSESSED')
        qsummary=quality.get('summary')
        qchecks=quality.get('checks')
        if qstatus=='PASS':
            st.success('EVENT LOG QUALITY GATE — PASSED ✓  All hard reconciliation/integrity checks passed and no review warnings remain.')
        elif qstatus=='WARN':
            st.warning('EVENT LOG QUALITY GATE — REVIEW REQUIRED ⚠  Hard checks passed, but one or more quality signals require analyst review.')
        elif qstatus=='FAIL':
            st.error('EVENT LOG QUALITY GATE — FAILED ✕  At least one hard integrity or reconciliation check failed. Do not treat this event log as validated until resolved.')
        else:
            st.warning('Event Log Quality Gate was not assessed for this run.')
        if isinstance(qsummary,pd.DataFrame) and not qsummary.empty:
            qr=qsummary.iloc[0]
            q1,q2,q3,q4=st.columns(4)
            q1.metric('Quality checks',int(qr.get('checks_total',0)))
            q2.metric('Passed',int(qr.get('checks_passed',0)))
            q3.metric('Warnings',int(qr.get('warnings',0)))
            q4.metric('Failures',int(qr.get('failures',0)))
        if isinstance(qchecks,pd.DataFrame) and not qchecks.empty:
            with st.expander('Inspect Event Log Quality Gate checks',expanded=qstatus!='PASS'):
                st.caption('PASS = reconciled/valid. WARN = technically accounted for but analyst review is recommended. FAIL = hard integrity/reconciliation problem.')
                st.dataframe(qchecks,use_container_width=True,hide_index=True)
            issue_records=r.get('quality_issue_records')
            actionable=qchecks[qchecks['status'].isin(['WARN','FAIL'])].copy()
            if isinstance(issue_records,pd.DataFrame) and not issue_records.empty:
                st.markdown('**Affected records requiring investigation**')
                st.caption('These records are shown because they caused an actionable event-generation quality issue. They were not silently dropped.')
                for _,check in actionable.iterrows():
                    cid=str(check.get('check_id'))
                    src=check.get('source'); rule=check.get('rule')
                    subset=issue_records[issue_records['Quality_Issue'].astype(str)==cid].copy()
                    if src is not None and 'Source' in subset.columns:
                        subset=subset[subset['Source'].astype(str)==str(src)]
                    if rule is not None and 'Event_Rule' in subset.columns:
                        subset=subset[subset['Event_Rule'].astype(str)==str(rule)]
                    if not subset.empty:
                        with st.expander(f"Inspect affected records — {cid} ({len(subset):,})",expanded=True):
                            preferred=[c for c in ['Source','Source_Row_Number','Case_ID','Event_Rule','Intended_Activity','Timestamp_Field','Timestamp_Original_Value','Quality_Reason'] if c in subset.columns]
                            rest=[c for c in subset.columns if c not in preferred]
                            st.dataframe(subset[preferred+rest],use_container_width=True,hide_index=True)
                            st.download_button(
                                f'Download {cid} affected records CSV',
                                subset[preferred+rest].to_csv(index=False).encode('utf-8'),
                                file_name=f'{cid}_affected_records.csv',mime='text/csv',
                                key=f'quality_issue_download_{cid}_{str(src)}_{str(rule)}'
                            )
        # Analyst disposition is intentionally separate from the technical Quality Gate.
        # A FAIL/WARN is never rewritten to PASS; the analyst may accept a documented exception.
        if isinstance(qchecks,pd.DataFrame) and not qchecks.empty:
            actionable=qchecks[qchecks['status'].isin(['WARN','FAIL'])].copy()
            if not actionable.empty:
                st.markdown('### Exception review & event log approval')
                st.caption(
                    'Technical findings remain unchanged. If investigation confirms an issue is acceptable for the intended analysis, '
                    'you may acknowledge it with a justification. This does not repair or hide the underlying data-quality finding.'
                )
                approvals=st.session_state.get('quality_exception_approvals',{})
                approval_rows=[]
                for idx,check in actionable.reset_index(drop=True).iterrows():
                    cid=str(check.get('check_id')); src=str(check.get('source')); rule=str(check.get('rule'))
                    exception_key=f'{cid}|{src}|{rule}|{idx}'
                    old=approvals.get(exception_key,{})
                    with st.expander(f"{check.get('status')} — {cid} · {src}",expanded=True):
                        acknowledged=st.checkbox(
                            'I reviewed this finding and accept it as an exception for this event log',
                            value=bool(old.get('acknowledged',False)),
                            key=f'qa_ack_{exception_key}'
                        )
                        justification=st.text_area(
                            'Justification / analyst decision',
                            value=str(old.get('justification','')),
                            placeholder='Explain why this exception is acceptable for the intended analysis.',
                            key=f'qa_reason_{exception_key}'
                        )
                        if acknowledged and not justification.strip():
                            st.warning('A justification is required before this exception can be considered acknowledged.')
                        approvals[exception_key]={
                            'check_id':cid,'technical_status':str(check.get('status')),
                            'source':src,'rule':rule,'acknowledged':bool(acknowledged and justification.strip()),
                            'justification':justification.strip()
                        }
                        approval_rows.append(approvals[exception_key])
                st.session_state.quality_exception_approvals=approvals
                approved_count=sum(1 for x in approval_rows if x['acknowledged'])
                all_approved=approved_count==len(approval_rows)
                st.write(f'Exceptions acknowledged: **{approved_count}/{len(approval_rows)}**')
                final_approve=st.checkbox(
                    'Approve event log with acknowledged exceptions',
                    value=False,
                    disabled=not all_approved,
                    key='approve_event_log_with_exceptions'
                )
                if final_approve and all_approved:
                    st.success('EVENT LOG RELEASE STATUS — VALIDATED WITH ACKNOWLEDGED EXCEPTIONS ✓')
                    st.caption('The technical Quality Gate findings remain recorded above; this is an explicit analyst disposition, not a technical PASS.')
                    approval_df=pd.DataFrame(approval_rows)
                    approval_payload={
                        'release_status':'VALIDATED WITH ACKNOWLEDGED EXCEPTIONS',
                        'technical_quality_gate':qstatus,
                        'project':st.session_state.get('project_name',''),
                        'exceptions':approval_rows
                    }
                    st.download_button(
                        'Download analyst exception approval (.json)',
                        json.dumps(approval_payload,indent=2).encode('utf-8'),
                        file_name='Analyst_Exception_Approval.json',mime='application/json'
                    )
                    st.download_button(
                        'Download acknowledged exceptions (.csv)',
                        approval_df.to_csv(index=False).encode('utf-8'),
                        file_name='Acknowledged_Quality_Exceptions.csv',mime='text/csv'
                    )
                elif all_approved:
                    st.info('All exceptions have been acknowledged. Check the final approval box above to release this event log as validated with acknowledged exceptions.')
                else:
                    st.warning('This event log is not approved. Review and justify every WARN/FAIL finding before final approval.')
        incremental=r.get('incremental_integration')
        duplicate_metric=(int(incremental.get('incoming_duplicates_within_batch',0))
                          if incremental else s.get('duplicate_candidates',0))
        a,b,c,d=st.columns(4)
        a.metric('Cases',s.get('cases',0))
        b.metric('Events',s.get('events',0))
        c.metric('Activities',s.get('activities',s.get('stages',0)))
        d.metric('Repeated signatures (QA)',duplicate_metric)
        if r.get('warnings'): st.warning('\n'.join(r['warnings']))
        if r.get('identity_stats'):
            ids=r['identity_stats']
            st.caption(f"Identity continuity — matched existing: {ids.get('matched_existing',0):,} · new assigned: {ids.get('new_assigned',0):,} · unknown excluded: {ids.get('unknown_excluded',0):,}")
        if r.get('incremental_integration'):
            inc=r['incremental_integration']
            st.info(
                f"Incremental integration: {int(inc['baseline_events']):,} baseline events preserved + "
                f"{int(inc['new_unique_events_added']):,} new events added = {int(inc['final_events']):,} final events. "
                f"Incoming already in baseline: {int(inc['incoming_events_already_in_baseline']):,}; "
                f"incoming repeated signatures (QA only): {int(inc['incoming_duplicates_within_batch']):,}."
            )
            if int(inc.get('baseline_duplicate_rows_qa_only',0)):
                st.caption(
                    f"Baseline QA only: {int(inc['baseline_duplicate_rows_qa_only']):,} rows participate in "
                    f"{int(inc['baseline_duplicate_signatures_qa_only']):,} repeated signatures. Baseline rows were not removed."
                )
            # The completed run is persisted in st.session_state.run_result as `r`,
            # so duplicate inspection survives Streamlit reruns and tab changes.
            dup_df=r.get('duplicate_inspection')
            if dup_df is not None and not dup_df.empty:
                with st.expander(
                    f"Inspect repeated incoming signatures — {int(inc['incoming_duplicate_groups']):,} groups / "
                    f"{int(inc['incoming_duplicate_rows_for_inspection']):,} rows",
                    expanded=False
                ):
                    st.caption(
                        "Rows are grouped because they share Case_ID + Activity + Timestamp + Source. "
                        "This is QA/discovery, not proof of duplication. All generated occurrences are retained unless an explicit activity-specific resolution rule was enabled."
                    )
                    st.dataframe(dup_df,use_container_width=True,hide_index=True)
                    st.download_button(
                        "Download duplicate inspection CSV",
                        data=dup_df.to_csv(index=False).encode('utf-8'),
                        file_name='incoming_duplicate_inspection.csv',
                        mime='text/csv'
                    )

        repeated=r.get('repeated_activity_occurrences')
        if isinstance(repeated,pd.DataFrame) and not repeated.empty:
            st.success(f"Configuration trigger saved: {len(st.session_state.get('multiplicity_discovery',[])):,} affected source/activity combinations are available in Events & mappings.")
            st.markdown('**Repeated activity occurrences — discovery**')
            st.caption('These activities occurred more than once for at least one Case_ID before any configured multiplicity resolution. Return to Events & mappings to configure each affected activity independently.')
            st.dataframe(repeated,use_container_width=True,hide_index=True)
        audit=r.get('multiplicity_resolution_audit')
        if isinstance(audit,pd.DataFrame) and not audit.empty:
            with st.expander(f'Multiplicity resolution audit — {(audit.Decision=="EXCLUDE").sum():,} excluded occurrences',expanded=False):
                st.dataframe(audit,use_container_width=True,hide_index=True)
                st.download_button('Download multiplicity resolution audit CSV',audit.to_csv(index=False).encode('utf-8'),file_name='multiplicity_resolution_audit.csv',mime='text/csv')

        ep=Path(r['paths']['event_log']); st.markdown('**Integrated event log preview**'); st.dataframe(pd.read_csv(ep).head(200),use_container_width=True)
        qdir=Path(r['paths']['qa_dir']); qfiles=list(qdir.glob('*.csv'))
        if qfiles:
            st.markdown('**QA / audit tables**'); qsel=st.selectbox('QA table',[p.name for p in qfiles])
            try:
                qdf=pd.read_csv(qdir/qsel)
                if len(qdf): st.dataframe(qdf,use_container_width=True)
                else: st.info('This QA table contains no records for this run.')
            except pd.errors.EmptyDataError:
                st.info('This QA table contains no records for this run.')
        validation_report=r.get('paths',{}).get('validation_report')
        if validation_report and Path(validation_report).exists():
            st.download_button('Download Event Log Validation Report (.zip)',Path(validation_report).read_bytes(),
                               file_name='Event_Log_Validation_Report.zip',mime='application/zip',
                               help='Reconciliation and quality evidence for this run: quality checks, source accounting, event-rule accounting, mapping QA, multiplicity QA, and temporal QA.')
        safe_package=Path(r['package'])
        st.download_button('Download Safe Results (.zip)',safe_package.read_bytes(),file_name='ProcessFlow_SAFE_Results.zip',mime='application/zip',
                           help='De-identified results only. Does not contain re-identification lookup tables.')
        restricted=r.get('restricted_package')
        if restricted and Path(restricted).exists():
            st.warning('The restricted package contains identity lookup tables. Store it securely and never publish it.')
            st.download_button('Download Complete Run — RESTRICTED (.zip)',Path(restricted).read_bytes(),
                               file_name='ProcessFlow_RESTRICTED_Results.zip',mime='application/zip')
        manifest=Path(r['paths']['manifest']); st.download_button('Download run manifest',manifest.read_bytes(),file_name='Run_Manifest.json',mime='application/json')
        vault_info=r.get('vault_summary',{})
        if vault_info:
            st.markdown('**Local identity vault**')
            st.caption(f"Lookup files created: {vault_info.get('lookup_files',0)} · identities represented: {vault_info.get('identity_rows',0)}. The local vault also persists for reuse during this run workspace.")


with tabs[5]:
    st.subheader('Automatic Process Analysis')
    st.caption('A standardized exploratory view of the final de-identified event log. These are descriptive process metrics, not project-specific business KPIs.')
    r=st.session_state.run_result
    if not r or 'error' in r:
        st.info('Run the pipeline successfully to generate the process analysis.')
    else:
        ep=Path(r['paths']['event_log']); events=pd.read_csv(ep)
        analysis=build_process_analysis(events)
        ov=analysis['overview']; vals=dict(zip(ov['Metric'],ov['Value'])) if len(ov) else {}
        a,b,c,d=st.columns(4)
        a.metric('Cases',vals.get('Cases',0)); b.metric('Events',vals.get('Events',0)); c.metric('Activities',vals.get('Activities',0)); d.metric('Process variants',vals.get('Process variants',0))
        e,f,g=st.columns(3)
        e.metric('Median events / case',vals.get('Events per case - median','—')); f.metric('Median case duration (days)',vals.get('Case duration days - median','—')); g.metric('P90 case duration (days)',vals.get('Case duration days - P90','—'))
        st.markdown('### Activity coverage')
        st.caption('Coverage = unique cases containing the activity at least once ÷ all cases. Low coverage is a review signal, not automatically a data-quality error.')
        cov=analysis['activity_coverage']; st.dataframe(cov,use_container_width=True,hide_index=True)
        if len(cov):
            st.bar_chart(cov.set_index('Activity')['Coverage_%'])
        with st.expander('Process variants',expanded=False): st.dataframe(analysis['variants'].head(50),use_container_width=True,hide_index=True)
        c1,c2=st.columns(2)
        with c1:
            st.markdown('### Start activities'); st.dataframe(analysis['start_activities'].head(20),use_container_width=True,hide_index=True)
        with c2:
            st.markdown('### End activities'); st.dataframe(analysis['end_activities'].head(20),use_container_width=True,hide_index=True)
        st.markdown('### Cases over time'); st.dataframe(analysis['monthly_cases'],use_container_width=True,hide_index=True)
        if len(analysis['monthly_cases']): st.line_chart(analysis['monthly_cases'].set_index('Month')[['Cases_Started','Cases_Ended']])
        with st.expander('Preserved attribute summary',expanded=False):
            if len(analysis['attribute_summary']): st.dataframe(analysis['attribute_summary'],use_container_width=True,hide_index=True)
            else: st.info('No additional preserved attributes were available for summary.')
        st.markdown('### Data-quality signals'); st.dataframe(analysis['data_quality'],use_container_width=True,hide_index=True)
        with st.expander('Metric definitions & interpretation guidance',expanded=False): st.dataframe(analysis['definitions'],use_container_width=True,hide_index=True)
        st.download_button('Download Automatic Process Analysis (.zip)',analysis_csv_package(analysis),file_name='Automatic_Process_Analysis.zip',mime='application/zip',help='Contains separate CSV tables plus metric definitions for review or sharing with an SME.')

st.divider(); st.caption('Use synthetic or authorized datasets only. Never publish restricted identity lookups.')
