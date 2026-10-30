from pathlib import Path
import pandas as pd


def inspect_excel(path):
    path = Path(path)
    xls = pd.ExcelFile(path)
    report = {}
    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        report[sheet] = {
            'rows': len(df), 'columns': list(df.columns),
            'dtypes': {c: str(t) for c,t in df.dtypes.items()},
            'null_counts': {c: int(v) for c,v in df.isna().sum().items()}
        }
    return report


def load_excel_source(path, sheet_name=0):
    df = pd.read_excel(path, sheet_name=sheet_name)
    if df.columns.duplicated().any():
        dup = list(df.columns[df.columns.duplicated()])
        raise ValueError(f'Duplicate column names detected: {dup}')
    return df

def load_table(path, sheet_name=0):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        df=pd.read_csv(path)
    else:
        df=load_excel_source(path,sheet_name=sheet_name)
    if df.columns.duplicated().any():
        dup=list(df.columns[df.columns.duplicated()])
        raise ValueError(f'Duplicate column names detected: {dup}')
    return df
