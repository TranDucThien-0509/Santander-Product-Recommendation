"""Read a single raw snapshot; preserve missing and invalid-value flags."""
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from .schema import at_month, require

FIELDS=['age','renta','antiguedad','canal_entrada','segmento','sexo','nomprov']
NUMERIC=['age','renta','antiguedad']
MISSING='__MISSING__'


def clean(d):
    d=d.copy()
    for c in FIELDS:
        raw=d[c].astype('string').str.strip().replace('',pd.NA)
        d[c+'_missing_raw']=raw.isna()
        if c in NUMERIC:
            v=pd.to_numeric(raw,errors='coerce').astype(float)
            invalid=raw.notna() & (v.isna() | ~np.isfinite(v) | v.lt(0))
            if c=='age': invalid |= v.gt(110)
            d[c+'_raw']=raw
            d[c+'_invalid']=invalid
            d[c]=v.mask(invalid)
        else:
            d[c]=raw.fillna(MISSING)
    return d


def load_raw(path, month):
    path=Path(path);parts=[]
    def consume(source):
        for q in pd.read_csv(source,usecols=['fecha_dato','ncodpers']+FIELDS,dtype='string',
                             na_values=['NA',' NA',''],chunksize=400000):
            dt=pd.to_datetime(q.fecha_dato,errors='coerce')
            require(dt.notna().all(),'raw: invalid date')
            q=q.loc[dt.dt.strftime('%Y-%m').eq(month)].copy()
            if len(q):parts.append(q)
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if Path(n).name=='train_ver2.csv']
            require(len(names)==1,'raw ZIP must contain one train_ver2.csv')
            with z.open(names[0]) as f:consume(f)
    else:consume(path)
    require(bool(parts),f'raw: no snapshot {month}')
    d=pd.concat(parts,ignore_index=True).rename(columns={'ncodpers':'customer_id'})
    d=at_month(d,month,'raw demographics')
    return clean(d.drop(columns='fecha_dato'))
