
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = "ERROR"
    source: str | None = None
    field: str | None = None
    suggestion: str | None = None
    def to_dict(self): return asdict(self)

def validate_project_config(cfg):
    issues=[]
    if not isinstance(cfg,dict):
        return [ValidationIssue("CFG_NOT_OBJECT","Project configuration must be an object.")]
    if not cfg.get("project"):
        issues.append(ValidationIssue("CFG_PROJECT_MISSING","Project metadata is missing.",suggestion="Add a project name and version."))
    sources=cfg.get("sources",[])
    if not sources:
        issues.append(ValidationIssue("CFG_NO_SOURCES","No data sources are configured.",suggestion="Register at least one source."))
    names=[]
    for s in sources:
        name=s.get("name")
        if not name:
            issues.append(ValidationIssue("CFG_SOURCE_NAME","A source is missing its name."))
        elif name in names:
            issues.append(ValidationIssue("CFG_SOURCE_DUPLICATE",f"Duplicate source name: {name}",source=name))
        names.append(name)
        if not s.get("path"):
            issues.append(ValidationIssue("CFG_SOURCE_PATH",f"Source '{name}' has no file path.",source=name))
        rules=s.get("event_rules",s.get("events",[]))
        if not rules:
            issues.append(ValidationIssue("CFG_NO_EVENT_RULES",f"Source '{name}' has no event rules.",source=name,
                                          suggestion="Define at least one timestamp/activity rule or mark the source transformation-only."))
    return issues

def blocking_issues(issues):
    return [x for x in issues if getattr(x,"severity","ERROR")=="ERROR"]
