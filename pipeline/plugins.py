
from __future__ import annotations
from abc import ABC
from dataclasses import dataclass, asdict
from typing import Any
import pandas as pd

@dataclass
class RuleAudit:
    project: str
    stage: str
    rule_id: str
    description: str
    input_count: int | None = None
    output_count: int | None = None
    excluded_count: int | None = None
    changed_count: int | None = None
    status: str = "PASS"
    detail: str | None = None

    def to_dict(self):
        return asdict(self)

class ProjectPlugin(ABC):
    """Stable extension contract for project-specific transformation logic."""
    name = "base"
    version = "0"

    def build_cohort(self, sources: dict[str, pd.DataFrame], context: dict[str, Any]):
        return None, []

    def pre_source(self, source_name: str, df: pd.DataFrame, context: dict[str, Any]):
        return df, []

    def post_source(self, source_name: str, events: pd.DataFrame, context: dict[str, Any]):
        return events, []

    def custom_validations(self, integrated_events: pd.DataFrame, context: dict[str, Any]):
        return []

    def project_qa(self, integrated_events: pd.DataFrame, context: dict[str, Any]):
        return {}

def audit_frame(items):
    rows=[]
    for x in items:
        rows.append(x.to_dict() if hasattr(x,"to_dict") else dict(x))
    return pd.DataFrame(rows)
