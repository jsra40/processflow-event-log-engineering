from pathlib import Path
import yaml

REQUIRED_TOP_LEVEL = {'project','privacy','sources','integration'}

def load_project_config(path):
    path=Path(path)
    with path.open(encoding='utf-8') as f:
        cfg=yaml.safe_load(f) or {}
    missing=sorted(REQUIRED_TOP_LEVEL-set(cfg))
    if missing: raise ValueError(f'Configuration missing sections: {missing}')
    if not cfg['sources']: raise ValueError('At least one source must be configured')
    names=[s.get('name') for s in cfg['sources']]
    if any(not n for n in names): raise ValueError('Every source requires a name')
    if len(names)!=len(set(names)): raise ValueError('Source names must be unique')
    return cfg
