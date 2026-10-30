import pandas as pd

def _normalize_key_pairs(keys=None, source_keys=None, mapping_keys=None):
    if source_keys is not None or mapping_keys is not None:
        source_keys=list(source_keys or []); mapping_keys=list(mapping_keys or [])
        if not source_keys or len(source_keys)!=len(mapping_keys):
            raise ValueError('Mapping source_keys and mapping_keys must be non-empty and have equal length')
        return source_keys,mapping_keys
    keys=list(keys or [])
    if not keys: raise ValueError('Mapping requires at least one key column')
    return keys,keys

def apply_mapping(df, mapping_df, keys=None, outputs=(), unmapped_policy='keep', source_keys=None, mapping_keys=None):
    source_keys,mapping_keys=_normalize_key_pairs(keys,source_keys,mapping_keys)
    missing=[c for c in source_keys if c not in df.columns]
    mmissing=[c for c in mapping_keys+list(outputs) if c not in mapping_df.columns]
    if missing: raise ValueError(f'Source mapping keys missing: {missing}')
    if mmissing: raise ValueError(f'Mapping columns missing: {mmissing}')
    if mapping_df.duplicated(mapping_keys).any():
        dup=mapping_df.loc[mapping_df.duplicated(mapping_keys,keep=False),mapping_keys]
        raise ValueError(f'Mapping contains duplicate key combinations: {dup.drop_duplicates().to_dict("records")[:10]}')
    marker='__mapping_hit__'
    # Normalize surrounding whitespace without changing case or source text semantics.
    left=df.copy(); right=mapping_df.copy()
    for c in source_keys:
        if c in left.columns and (pd.api.types.is_object_dtype(left[c]) or pd.api.types.is_string_dtype(left[c])):
            left[c]=left[c].map(lambda x: x.strip() if isinstance(x,str) else x)
    for c in mapping_keys:
        if c in right.columns and (pd.api.types.is_object_dtype(right[c]) or pd.api.types.is_string_dtype(right[c])):
            right[c]=right[c].map(lambda x: x.strip() if isinstance(x,str) else x)
    rename={m:s for s,m in zip(source_keys,mapping_keys) if s!=m}
    m=right[mapping_keys+list(outputs)].copy().rename(columns=rename); m[marker]=True
    out=left.merge(m,on=source_keys,how='left',validate='many_to_one')
    hit=out[marker].eq(True); total=len(out); mapped=int(hit.sum())
    unmapped_keys=out.loc[~hit,source_keys].drop_duplicates().reset_index(drop=True)
    diag={'rows_total':total,'rows_mapped':mapped,'rows_unmapped':total-mapped,'coverage':mapped/total if total else 1.0,'unmapped_keys':unmapped_keys}
    if unmapped_policy not in {'keep','drop','error'}: raise ValueError('unmapped_policy must be keep, drop, or error')
    if unmapped_policy=='drop': out=out.loc[hit].copy()
    elif unmapped_policy=='error' and (~hit).any(): raise ValueError(f'Unmapped rows detected: {total-mapped}')
    return out.drop(columns=[marker]),diag
