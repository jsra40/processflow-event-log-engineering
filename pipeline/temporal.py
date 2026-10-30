
from __future__ import annotations
import pandas as pd
import re

_DATE_ONLY_RE=re.compile(r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*$")

def infer_timestamp_precision(raw):
    """Best-effort precision classification before pandas fills missing time with midnight."""
    if pd.isna(raw): return "missing"
    if isinstance(raw, pd.Timestamp):
        return "date" if raw.hour==raw.minute==raw.second==raw.microsecond==0 else "datetime"
    # Python datetime/date and Excel-parsed cells
    if hasattr(raw,"hour"):
        return "date" if getattr(raw,"hour",0)==getattr(raw,"minute",0)==getattr(raw,"second",0)==0 else "datetime"
    s=str(raw).strip()
    if _DATE_ONLY_RE.match(s): return "date"
    return "datetime" if any(x in s for x in (":","T")) else "date"

def apply_temporal_order(events, constraints):
    """
    Enforce only same-calendar-day ambiguous ordering when at least one event is date precision.
    Cross-date violations are reported, never silently rewritten.
    constraints: [{"before":"Decision to Treat","after":"Ready to Treat"}]
    """
    out=events.copy()
    if "Timestamp_Original" not in out:
        out["Timestamp_Original"]=out["Timestamp"]
    if "Timestamp_Precision" not in out:
        out["Timestamp_Precision"]="datetime"
    out["Timestamp_Adjusted"]=False
    out["Timestamp_Adjustment_Reason"]=pd.NA
    violations=[]
    for c in constraints or []:
        before,after=c["before"],c["after"]
        for case_id,g in out.groupby("Case_ID",sort=False):
            bi=g.index[g["Activity"].eq(before)].tolist()
            ai=g.index[g["Activity"].eq(after)].tolist()
            if not bi or not ai: continue
            b,a=bi[0],ai[0]
            bt,at=pd.Timestamp(out.at[b,"Timestamp"]),pd.Timestamp(out.at[a,"Timestamp"])
            if bt < at: continue
            same_day=bt.date()==at.date()
            ambiguous=(out.at[b,"Timestamp_Precision"]=="date" or out.at[a,"Timestamp_Precision"]=="date")
            if same_day and ambiguous:
                # Preserve any known datetime as anchor; order ambiguous date-only values around it.
                if out.at[b,"Timestamp_Precision"]=="date" and out.at[a,"Timestamp_Precision"]=="datetime":
                    new_b=at-pd.Timedelta(seconds=1)
                    out.at[b,"Timestamp"]=new_b
                    out.at[b,"Timestamp_Adjusted"]=True
                    out.at[b,"Timestamp_Adjustment_Reason"]=f"same-day missing-time precision; enforced {before} before {after}"
                else:
                    new_a=bt+pd.Timedelta(seconds=1)
                    out.at[a,"Timestamp"]=new_a
                    out.at[a,"Timestamp_Adjusted"]=True
                    out.at[a,"Timestamp_Adjustment_Reason"]=f"same-day missing-time precision; enforced {before} before {after}"
            else:
                violations.append({"Case_ID":case_id,"before_activity":before,"after_activity":after,
                                   "before_timestamp":bt,"after_timestamp":at,
                                   "reason":"cross-date or fully-timed temporal-order violation"})
    return out,pd.DataFrame(violations)
