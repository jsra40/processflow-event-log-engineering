
from __future__ import annotations
from pathlib import Path
import json, re

def safe_project_slug(name):
    slug=re.sub(r"[^A-Za-z0-9._-]+","_",str(name).strip()).strip("._")
    return slug or "project"

def ensure_workspace(base, project_name):
    root=Path(base)/safe_project_slug(project_name)
    paths={
        "root":root,
        "config":root/"config",
        "input":root/"input",
        "mappings":root/"mappings",
        "output":root/"output",
        "secure_local":root/"secure_local",
        "logs":root/"logs",
    }
    for p in paths.values(): p.mkdir(parents=True,exist_ok=True)
    return paths

def save_project_config(paths, config, filename="project.json"):
    p=paths["config"]/filename
    p.write_text(json.dumps(config,indent=2,default=str))
    return p
