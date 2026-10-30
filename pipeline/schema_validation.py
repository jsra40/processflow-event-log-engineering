def validate_columns(df, required_columns):
    missing = [c for c in required_columns if c not in df.columns]
    return {'ok': not missing, 'missing_columns': missing}
