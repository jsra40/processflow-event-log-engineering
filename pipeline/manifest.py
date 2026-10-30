from pathlib import Path
from datetime import datetime, timezone
import hashlib, json

def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def build_manifest(project, config_path, inputs, mapping_files, summary, warnings=None, status='success'):
    def entry(p):
        p=Path(p); return {'name':p.name,'sha256':sha256_file(p),'size_bytes':p.stat().st_size}
    return {
        'pipeline_version':'0.3.0',
        'project':project,
        'run_timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'status':status,
        'config':entry(config_path),
        'inputs':[entry(p) for p in inputs],
        'mappings':[entry(p) for p in mapping_files],
        'summary':summary,
        'warnings':warnings or [],
    }

def write_manifest(manifest, path):
    Path(path).write_text(json.dumps(manifest,indent=2,default=str),encoding='utf-8')
