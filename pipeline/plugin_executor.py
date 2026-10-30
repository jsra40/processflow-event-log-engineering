
from __future__ import annotations
import pandas as pd
from .plugins import audit_frame

def execute_project_plugin(plugin, sources, event_builders=None, context=None):
    """
    Generic project orchestration boundary.
    event_builders maps source name -> callable(df)->events.
    """
    context={} if context is None else dict(context)
    sources={k:v.copy() for k,v in sources.items()}
    audit=[]

    cohort, a = plugin.build_cohort(sources, context)
    audit.extend(a or [])
    if cohort is not None:
        context["cohort"]=cohort

    all_events=[]
    for name,df in sources.items():
        transformed,a=plugin.pre_source(name,df,context)
        audit.extend(a or [])
        if event_builders and name in event_builders:
            events=event_builders[name](transformed)
            events,a=plugin.post_source(name,events,context)
            audit.extend(a or [])
            if events is not None and len(events):
                all_events.append(events)

    if all_events:
        integrated=pd.concat(all_events,ignore_index=True)
        if {"Case_ID","timestamp","activity"}.issubset(integrated.columns):
            integrated["timestamp"]=pd.to_datetime(integrated["timestamp"],errors="coerce")
            integrated=integrated.sort_values(["Case_ID","timestamp","activity"]).reset_index(drop=True)
    else:
        integrated=pd.DataFrame(columns=["Case_ID","activity","timestamp","Source"])

    audit.extend(plugin.custom_validations(integrated,context) or [])
    qa=plugin.project_qa(integrated,context) or {}
    return {"cohort":cohort,"events":integrated,"audit":audit_frame(audit),"qa":qa,"context":context}
