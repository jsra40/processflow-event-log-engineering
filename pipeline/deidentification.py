import pandas as pd

ALLOWED_ACTIONS = {'pseudonymize','remove','keep','ignore','transformation_only'}

def apply_privacy_actions(df, identity_fields, vault):
    out=df.copy()
    audit=[]
    for col, rule in identity_fields.items():
        if col not in out.columns:
            audit.append({'column':col,'action':rule.get('action'),'status':'missing'})
            continue
        action=rule.get('action')
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f'Unsupported privacy action {action!r} for {col}')
        if action == 'pseudonymize':
            namespace=rule.get('namespace') or rule.get('class') or 'identity'
            prefix=rule.get('prefix','ID_')
            target=rule.get('target_column') or ('Case_ID' if rule.get('class')=='case' else f'{col}_ID')
            out[target]=vault.pseudonymize(out[col].tolist(), namespace, prefix, int(rule.get('width',6)))
            if rule.get('drop_original', True): out=out.drop(columns=[col])
        elif action in {'remove','ignore'}:
            out=out.drop(columns=[col])
        # keep and transformation_only stay available during processing; export layer can remove transformation_only later.
        audit.append({'column':col,'action':action,'status':'applied'})
    return out, pd.DataFrame(audit)
