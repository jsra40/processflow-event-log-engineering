from .privacy import scan_columns

PROHIBITED_ACTIONS={'remove','pseudonymize','transformation_only','ignore'}

def final_privacy_gate(columns, identity_fields):
    unresolved=[]
    safe_targets={'Case_ID'} | {r.get('target_column') for r in identity_fields.values() if r.get('target_column')}
    configured=set(identity_fields)
    for finding in scan_columns(columns):
        col=finding['column']
        if col in safe_targets:
            continue
        if finding['review_required'] and col not in configured:
            unresolved.append({'column':col,'reason':'potential identifier is not classified'})
        elif col in identity_fields and identity_fields[col].get('action') in PROHIBITED_ACTIONS:
            unresolved.append({'column':col,'reason':f"raw field remains after action={identity_fields[col].get('action')}"})
    return {'ok':not unresolved,'unresolved':unresolved}
