"""Input contracts. Do not replace explicit validation with Python assert."""
import numpy as np
import pandas as pd

PRODUCTS = ['ind_ahor_fin_ult1','ind_aval_fin_ult1','ind_cco_fin_ult1','ind_cder_fin_ult1',
'ind_cno_fin_ult1','ind_ctju_fin_ult1','ind_ctma_fin_ult1','ind_ctop_fin_ult1',
'ind_ctpp_fin_ult1','ind_deco_fin_ult1','ind_deme_fin_ult1','ind_dela_fin_ult1',
'ind_ecue_fin_ult1','ind_fond_fin_ult1','ind_hip_fin_ult1','ind_plan_fin_ult1',
'ind_pres_fin_ult1','ind_reca_fin_ult1','ind_tjcr_fin_ult1','ind_valo_fin_ult1',
'ind_viv_fin_ult1','ind_nomina_ult1','ind_nom_pens_ult1','ind_recibo_ult1']
STATES = ['New','Active','At-risk','Churned','Win-back']
PIDS = ['P1','P2','P3','P4','P5','P6']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def columns(d, needed, name):
    require(set(needed).issubset(d.columns), f'{name}: missing columns {set(needed)-set(d.columns)}')


def unique(d, name):
    columns(d, ['customer_id'], name)
    d = d.copy()
    v = pd.to_numeric(d.customer_id, errors='raise')
    require(v.notna().all() and np.isfinite(v).all() and v.mod(1).eq(0).all(), f'{name}: invalid customer_id')
    d['customer_id'] = v.astype('int64')
    require(d.customer_id.is_unique, f'{name}: duplicate customer_id')
    return d


def at_month(d, month, name):
    d = unique(d, name)
    available = [c for c in ['as_of_month','month','record_date','fecha_dato','month_idx'] if c in d]
    require(bool(available), f'{name}: no month field')
    for c in available:
        if c == 'month_idx':
            per = pd.Period(month, 'M')
            require(pd.to_numeric(d[c], errors='coerce').eq(per.year*12+per.month).all(), f'{name}: wrong month_idx')
        else:
            values = pd.to_datetime(d[c].astype(str), errors='coerce').dt.strftime('%Y-%m')
            require(values.eq(month).all(), f'{name}: wrong or missing {c}')
    return d


def subset(d, base, name):
    require(set(d.customer_id).issubset(set(base.customer_id)), f'{name}: IDs outside known population')


def truth(s, name):
    require(s.notna().all() and s.isin([True, False]).all(), f'{name}: missing/nonboolean flags')
    return s.astype(bool)
