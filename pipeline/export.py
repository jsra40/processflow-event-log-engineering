from pathlib import Path
import json

def export_run(output_dir, events, qa_tables, manifest, unmapped_tables=None):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    events_path=out/'Integrated_Event_Log.csv'
    events.to_csv(events_path,index=False)
    qa_dir=out/'qa'; qa_dir.mkdir(exist_ok=True)
    for name,df in qa_tables.items(): df.to_csv(qa_dir/f'{name}.csv',index=False)
    if unmapped_tables:
        udir=out/'unmapped'; udir.mkdir(exist_ok=True)
        for name,df in unmapped_tables.items():
            if df is not None and len(df): df.to_csv(udir/f'{name}.csv',index=False)
    manifest_path=out/'Run_Manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2,default=str),encoding='utf-8')
    return {'event_log':str(events_path),'manifest':str(manifest_path),'qa_dir':str(qa_dir)}
