from pathlib import Path
import csv, hashlib, json
import pandas as pd

class UnknownIdentityError(ValueError):
    pass

class LocalIdentityVault:
    def __init__(self, root, case_mode='allow_new'):
        self.root=Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.case_mode=case_mode
        self.stats={'matched_existing':0,'new_assigned':0,'unknown_excluded':0}

    def _path(self, namespace): return self.root / f'{namespace}_lookup.csv'

    def _load(self, namespace):
        p=self._path(namespace); mapping={}
        if p.exists():
            with p.open(newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    mapping[str(row['original_value']).strip()]=str(row['pseudonym']).strip()
        return mapping

    @staticmethod
    def read_lookup_table(source):
        source=Path(source)
        suffix=source.suffix.lower()
        if suffix in {'.xlsx','.xlsm','.xls'}:
            df=pd.read_excel(source,dtype=str)
        elif suffix=='.csv':
            # utf-8-sig safely consumes a BOM while remaining compatible with normal UTF-8.
            df=pd.read_csv(source,dtype=str,encoding='utf-8-sig')
        else:
            raise ValueError('Identity lookup must be a CSV or Excel workbook (.csv, .xlsx, .xlsm, .xls).')
        normalized={c:str(c).replace('\ufeff','').strip().lower() for c in df.columns}
        df=df.rename(columns=normalized)
        required={'original_value','pseudonym'}
        missing=required-set(df.columns)
        if missing:
            detected=', '.join(map(str,df.columns)) or '(none)'
            raise ValueError(f"Identity lookup is missing required column(s): {', '.join(sorted(missing))}. Detected columns: {detected}")
        return df

    def import_lookup(self, source, namespace='case'):
        df=self.read_lookup_table(source)
        if df.empty:
            raise ValueError('Identity lookup contains the required headers but has no identity rows.')
        incoming={}
        for _,r in df.iterrows():
            original='' if pd.isna(r['original_value']) else str(r['original_value']).strip()
            pseudo='' if pd.isna(r['pseudonym']) else str(r['pseudonym']).strip()
            if not original:
                continue
            if not pseudo:
                raise ValueError(f'Identity lookup has a blank pseudonym for original identifier {original}.')
            if original in incoming and incoming[original]!=pseudo:
                raise ValueError(f'Identity lookup assigns multiple pseudonyms to original identifier {original}.')
            incoming[original]=pseudo
        if len(set(incoming.values())) != len(incoming):
            raise ValueError('Identity lookup contains duplicate pseudonyms')
        current=self._load(namespace)
        for k,v in incoming.items():
            if k in current and current[k]!=v:
                raise ValueError(f'Immutable identity conflict for {k}')
            if v in current.values() and current.get(k)!=v:
                raise ValueError(f'Pseudonym {v} is already assigned to another identifier')
        current.update(incoming); self._save(namespace,current)
        return len(incoming)

    def pseudonymize(self, values, namespace, prefix, width=6):
        mapping=self._load(namespace)
        used=[]
        for p in mapping.values():
            try: used.append(int(p.split('_')[-1] if '_' in p else p[len(prefix):]))
            except Exception: pass
        next_id=max(used, default=0)+1
        out=[]
        for value in values:
            if value is None or str(value).strip()=='' or str(value).lower()=='nan':
                out.append(None); continue
            key=str(value).strip()
            if key in mapping:
                out.append(mapping[key])
                if namespace=='case': self.stats['matched_existing']+=1
                continue
            if namespace=='case' and self.case_mode=='existing_only':
                out.append(None); self.stats['unknown_excluded']+=1
                continue
            mapping[key]=f'{prefix}{next_id:0{width}d}'; next_id+=1
            out.append(mapping[key])
            if namespace=='case': self.stats['new_assigned']+=1
        self._save(namespace,mapping)
        return out

    def _save(self, namespace, mapping):
        p=self._path(namespace)
        with p.open('w', newline='', encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=['original_value','pseudonym']); w.writeheader()
            for k,v in mapping.items(): w.writerow({'original_value':k,'pseudonym':v})

    def identity_fingerprint(self, namespace='case'):
        mapping=self._load(namespace)
        canonical='\n'.join(f'{k}\t{mapping[k]}' for k in sorted(mapping))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def write_identity_manifest(self, project_name, namespace='case'):
        mapping=self._load(namespace)
        manifest={'project':project_name,'namespace':namespace,'lookup_records':len(mapping),
                  'identity_fingerprint':self.identity_fingerprint(namespace),
                  'rule':'Existing original identifiers never change pseudonym within this project identity.'}
        p=self.root/'Identity_Manifest.json'
        p.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        return p
