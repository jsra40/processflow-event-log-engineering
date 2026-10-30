import re

PATTERNS = {
    'person_identifier': [r'customer.?id', r'employee.?id', r'account.?id', r'person.?id'],
    'person_name': [r'customer.*name', r'first.*name', r'last.*name', r'surname'],
    'staff_identifier': [r'staff.*name', r'employee.*name', r'agent.*name'],
    'staff_username': [r'user.?name', r'user.?id', r'login', r'network.?id'],
    'quasi_identifier': [r'(^|_)dob($|_)', r'date.*birth', r'postal', r'address', r'phone', r'e.?mail'],
}

def normalize(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).strip().lower()).strip('_')

def scan_columns(columns):
    findings=[]
    for col in columns:
        n=normalize(col); hits=[]
        for cls, pats in PATTERNS.items():
            if any(re.search(p,n) for p in pats): hits.append(cls)
        findings.append({'column': col, 'normalized': n, 'flags': hits, 'review_required': bool(hits)})
    return findings

def require_reviewed_classification(columns, classifications):
    missing=[c for c in columns if c not in classifications]
    if missing:
        raise ValueError(f'Privacy classification missing for columns: {missing}')
    return True
