def event_log_summary(events):
    return {
        'cases': int(events['Case_ID'].nunique()) if 'Case_ID' in events else 0,
        'events': int(len(events)),
        'activities': int(events['Activity'].nunique()) if 'Activity' in events else 0,
        'sources': int(events['Source'].nunique()) if 'Source' in events else 0,
        'missing_case_id': int(events['Case_ID'].isna().sum()) if 'Case_ID' in events else None,
        'missing_activity': int(events['Activity'].isna().sum()) if 'Activity' in events else None,
        'missing_timestamp': int(events['Timestamp'].isna().sum()) if 'Timestamp' in events else None,
    }
