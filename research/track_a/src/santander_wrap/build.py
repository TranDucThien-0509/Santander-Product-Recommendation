"""Wrap already fitted outputs into a current-month customer table and ranked offers."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from .schema import PRODUCTS, STATES, PIDS, require, columns, at_month, unique, subset, truth
from .demographics import load_raw, FIELDS, NUMERIC, MISSING
from .cards import make_cards


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rfm_tags(d, edges):
    d=d.copy()
    finite=np.isfinite(d[['R','F_event_months','M_group_points']].to_numpy(dtype=float,na_value=np.nan)).all(axis=1)
    valid=d.is_observed & d.products_complete.eq(True) & d.F_event_months.gt(0) & finite
    require(d.loc[valid,'R'].ge(0).all(),'negative R')
    require(d.loc[valid,'M_group_points'].between(0,100).all(),'M_group_points outside 0..100')
    d['rfm_cluster']=pd.Series(pd.NA,index=d.index,dtype='string')
    if valid.any():
        tags=[]
        for feature,prefix in [('R','R'),('F_event_months','F'),('M_group_points','M')]:
            edge=np.asarray(edges[feature],float)
            require(len(edge)>=2 and np.all(np.diff(edge)>0),f'Invalid edges: {feature}')
            cut=pd.cut(d.loc[valid,feature],edge,labels=False,include_lowest=True)
            require(cut.notna().all(),f'RFM edges do not cover {feature}')
            tags.append(prefix+(cut.astype(int)+1).astype(str))
        d.loc[valid,'rfm_cluster']=tags[0]+'_'+tags[1]+'_'+tags[2]
    d['rfm_status']=np.select([~d.is_observed,d.F_event_months.eq(0).fillna(False),valid],
        ['NoCurrentSnapshot','NoObservedEvent','Assigned'],default='InvalidFeatures')
    return d


def persona_expected(d):
    f=d.F_event_months;n=d.n_products
    return np.select([f.eq(0)&n.le(2),f.eq(0)&n.ge(3),f.eq(1),f.ge(2)&n.le(1),
        f.ge(2)&n.between(2,4),f.ge(2)&n.ge(5)],PIDS,default='Invalid')


def load_recommendations(folder, month, method):
    folder=Path(folder)/'product_recommendation'/month/method
    parts=sorted(folder.glob('part_*.parquet'));statuses=sorted(folder.glob('status_*.parquet'))
    require(bool(parts) and bool(statuses),f'No recommendation parts/statuses in {folder}')
    rec=at_month(pd.concat([pd.read_parquet(p,columns=['customer_id','as_of_month','method','products','ranking_scores']) for p in parts],ignore_index=True),month,'recommendations')
    status=unique(pd.concat([pd.read_parquet(p) for p in statuses],ignore_index=True),'rec statuses')
    columns(rec,['method','products','ranking_scores'],'recommendations')
    columns(status,['catalog_status','scoring_method'],'rec statuses')
    require(rec.method.eq(method).all(),'recommendation method mismatch')
    require(set(rec.customer_id)==set(status.customer_id),'recommendation/status populations differ')
    return rec.merge(status,on='customer_id',validate='one_to_one'),parts+statuses


def build(config):
    c=config;p={k:Path(v) for k,v in c['paths'].items()};m=c['as_of_month'];h=c['clv_horizon_months']
    require(str(pd.Period(m,'M'))==m,'month must be YYYY-MM')
    require(c['clv_target']=='acquisitions' and h==1,'v1 primary export supports acquisitions / 1m')
    require(c['rfm_method']=='Hybrid_REDA_F4_M5','v1 final RFM method must match documented F4')
    used=[]
    def read(path,name):
        used.append(path)
        return at_month(pd.read_parquet(path),m,name)
    def cfg(path):
        used.append(path);return read_json(path)
    life=read(p['lifecycle_dir']/f'lifecycle_{m}.parquet','lifecycle')
    columns(life,['is_observed','lifecycle','rule_version','missing_months'],'lifecycle')
    require(len(life)>0,'empty known population')
    life['is_observed']=truth(life.is_observed,'is_observed')
    require(life.lifecycle.isin(STATES).all(),'unknown lifecycle')
    require(life.rule_version.eq(c['lifecycle_rule_version']).all(),'lifecycle version mismatch')
    require(life.is_observed.eq(life.lifecycle.isin(['New','Active','Win-back'])).all(),'lifecycle/presence mismatch')
    require(life.loc[life.lifecycle.eq('Churned'),'missing_months'].ge(6).all(),'Churned gap must be >=6')
    require(life.loc[life.lifecycle.eq('At-risk'),'missing_months'].between(1,5).all(),'At-risk gap must be 1..5')
    require(life.loc[life.is_observed,'missing_months'].eq(0).all(),'Observed gap must be 0')
    features=read(p['rfm_features_dir']/f'rfm_{m}.parquet','RFM features')
    needed=['R','F_event_months','F_events','M_group_points','M_n_products','products_complete']
    columns(features,needed,'RFM features')
    require(set(features.customer_id)==set(life.loc[life.is_observed,'customer_id']),'RFM snapshots differ from lifecycle')
    features['products_complete']=truth(features.products_complete,'products_complete')
    for col in ['F_event_months','F_events']:
        v=pd.to_numeric(features[col],errors='coerce')
        require(v.notna().all() and np.isfinite(v).all() and v.ge(0).all() and v.mod(1).eq(0).all(),f'invalid {col}')
    require(features.F_events.ge(features.F_event_months).all(),'F_events < event months')
    require(features.F_events.eq(0).eq(features.F_event_months.eq(0)).all(),'inconsistent event history')
    base=life[['customer_id','is_observed','lifecycle','missing_months','rule_version']].rename(columns={'rule_version':'lifecycle_version'})
    base=base.merge(features[['customer_id']+needed],on='customer_id',how='left',validate='one_to_one')
    base=base.rename(columns={'M_n_products':'n_products'})
    base['as_of_month']=m
    rconfig=cfg(p['rfm_model_dir']/'config.json')
    require(rconfig['fit_month']==c['rfm_fit_month'] and rconfig['fit_month']<=m,'RFM fit month mismatch/future')
    specs=cfg(p['rfm_model_dir']/'bucket_specs.json')
    require(c['rfm_method'] in specs,'RFM method unavailable')
    base=rfm_tags(base,specs[c['rfm_method']]);base['rfm_method']=c['rfm_method'];base['rfm_fit_month']=c['rfm_fit_month']

    pcfg=cfg(p['persona_dir']/'config.json')
    require(pcfg['version']==c['persona_version'] and pcfg.get('USE_M') is False,'persona config mismatch')
    require(pcfg['fit_label_month']<=m,'persona future fit label')
    persona=read(p['persona_dir']/f'personas_tree_{m}.parquet','persona')
    columns(persona,['persona_id','valid_pairs'],'persona')
    subset(persona,base,'persona')
    require(persona.persona_id.isin(PIDS).all(),'invalid persona_id')
    aligned=persona[['customer_id','persona_id','valid_pairs']].merge(base,on='customer_id',validate='one_to_one')
    require(aligned.is_observed.all() and aligned.products_complete.eq(True).all(),'persona contains absent/incomplete customers')
    require(aligned.valid_pairs.ge(3).all(),'persona has too little history')
    require((persona_expected(aligned)==aligned.persona_id).all(),'P1-P6 rules mismatch')
    base=base.merge(persona[['customer_id','persona_id','valid_pairs']].rename(columns={'valid_pairs':'persona_valid_pairs'}),on='customer_id',how='left',validate='one_to_one')
    base['persona_version']=c['persona_version']
    base['persona_status']=np.select([base.persona_id.notna(),~base.is_observed,~base.products_complete.eq(True)],
        ['Assigned','ExcludedNoCurrentSnapshot','ExcludedIncompleteSnapshot'],default='ExcludedHistoryOrInvalidFeatures')

    raw=load_raw(p['raw_csv_or_zip'],m);used.append(p['raw_csv_or_zip'])
    require(set(raw.customer_id)==set(features.customer_id),'raw/feature snapshot populations differ')
    base=base.merge(raw,on='customer_id',how='left',validate='one_to_one')
    base['demographics_status']=np.where(base.is_observed,'current_snapshot','no_current_snapshot')

    current=unique(pd.read_parquet(p['snapshot_cache_dir']/f'{m}.parquet'),'product snapshot')
    # Cache has no month field: the partition name supplies month; compare IDs/products to current features.
    used.append(p['snapshot_cache_dir']/f'{m}.parquet')
    columns(current,PRODUCTS,'product snapshot')
    require(current[PRODUCTS].isin([0,1]).all().all(),'snapshot not complete binary')
    require(set(current.customer_id)==set(features.loc[features.products_complete,'customer_id']),'cache/complete snapshot mismatch')
    nc=current.set_index('customer_id')[PRODUCTS].sum(axis=1)
    aligned_n=base.set_index('customer_id').n_products.reindex(nc.index)
    require(aligned_n.eq(nc).all(),'product count mismatch')

    selection=cfg(p['clv_dir']/'selection.json')
    require(selection['selected_by_horizon'][str(h)]['acquisitions']==c['clv_method'],'CLV method differs from validation selection')
    ccfg=cfg(p['clv_dir']/'config.json')
    require(ccfg['selected_by_horizon'][str(h)]['acquisitions']==c['clv_method'],'CLV config/selection mismatch')
    predictions=read(p['clv_dir']/f'clv_predictions_{m}_{h}m.parquet','CLV predictions')
    columns(predictions,['horizon_months','predicted_acquisitions','method_acquisitions','lifecycle'],'CLV predictions')
    require(predictions.horizon_months.eq(h).all() and predictions.method_acquisitions.eq(c['clv_method']).all(),'wrong CLV target/model/horizon')
    val=pd.to_numeric(predictions.predicted_acquisitions,errors='coerce')
    require(val.notna().all() and np.isfinite(val).all() and val.ge(0).all(),'invalid CLV prediction')
    require(set(predictions.customer_id)==set(current.customer_id),'CLV must cover current complete snapshots')
    pl=predictions[['customer_id','lifecycle']].merge(base[['customer_id','lifecycle']],on='customer_id',validate='one_to_one')
    require(pl.lifecycle_x.eq(pl.lifecycle_y).all(),'CLV/lifecycle mismatch')
    clv_cols=['customer_id','predicted_acquisitions','method_acquisitions']
    if 'rfm_cluster' in predictions:clv_cols.append('rfm_cluster')
    base=base.merge(predictions[clv_cols].rename(columns={'predicted_acquisitions':'expected_acquisitions',
        'method_acquisitions':'clv_method','rfm_cluster':'clv_source_rfm_cluster'}),on='customer_id',how='left',validate='one_to_one')
    base['clv_horizon_months']=h;base['clv_target']='acquisitions'
    base['clv_status']=np.select([base.expected_acquisitions.notna(),~base.is_observed],
        ['PredictedCurrentComplete','ExcludedNoCurrentSnapshot'],default='ExcludedIncompleteSnapshot')

    acfg=cfg(p['affinity_dir']/'selection.json')
    require(acfg['selected_method']==c['recommendation_method'],'affinity differs from validation selection')
    require(acfg['validation_month']<=m and acfg.get('window')==3,'unexpected affinity validation/window')
    rec,rec_files=load_recommendations(p['affinity_dir'],m,c['recommendation_method']);used.extend(rec_files)
    require(set(rec.customer_id)==set(base.customer_id),'recommendations do not cover known population')
    require(rec.catalog_status.isin(['current_complete','last_complete_snapshot','no_complete_snapshot']).all(),'unknown catalog status')
    complete=rec.catalog_status.eq('current_complete')
    require(set(rec.loc[complete,'customer_id'])==set(current.customer_id),'recommendation catalog/current cache mismatch')
    require(rec.loc[complete,'scoring_method'].eq(c['recommendation_method']).all(),'current scoring method mismatch')
    require(rec.loc[~complete,'scoring_method'].eq('popularity_fallback').all(),'stale scores must be flagged fallback')
    owned=current.set_index('customer_id')[PRODUCTS]
    owned_array=owned.to_numpy(dtype='uint8')
    product_ix={p:i for i,p in enumerate(PRODUCTS)}
    out=p['output_dir'];out.mkdir(parents=True,exist_ok=True)
    rec_out=out/f'recommendations_{m}'
    require(not rec_out.exists(),f'Output already exists: {rec_out}; use a new output directory to avoid stale parts')
    rec_out.mkdir()
    lists=[];top1=[];recommendation_rows=0
    for start in range(0,len(rec),25000):
        chunk=rec.iloc[start:start+25000]
        positions=owned.index.get_indexer(chunk.customer_id)
        long=[]
        for offset,row in enumerate(chunk.itertuples(index=False)):
            prods=list(row.products);scores=list(row.ranking_scores)
            require(len(prods)==len(scores) and len(prods)<=7 and len(prods)==len(set(prods)),'bad product ranking length/duplicates')
            require(set(prods).issubset(PRODUCTS),'unknown product name')
            require(np.isfinite(np.asarray(scores,float)).all(),'invalid recommendation scores')
            require(all(scores[i]>=scores[i+1] for i in range(len(scores)-1)),'ranking scores not descending')
            if row.catalog_status=='current_complete':
                x=owned_array[positions[offset]]
                require(not any(x[product_ix[p]]==1 for p in prods),'recommendation contains owned product')
                require(len(prods)==min(7,24-int(x.sum())),'incomplete current top7')
            lists.append((row.customer_id,json.dumps(prods)))
            if prods:top1.append((row.customer_id,prods[0],row.catalog_status))
            for rank,(prod,score) in enumerate(zip(prods,scores),1):
                long.append(dict(customer_id=row.customer_id,as_of_month=m,rank=rank,product=prod,ranking_score=score,
                    recommendation_method=row.method,scoring_method=row.scoring_method,catalog_status=row.catalog_status))
        long=pd.DataFrame(long,columns=['customer_id','as_of_month','rank','product','ranking_score','recommendation_method','scoring_method','catalog_status'])
        long.to_parquet(rec_out/f'part_{start:07d}.parquet',index=False)
        recommendation_rows+=len(long)
    base=base.merge(pd.DataFrame(lists,columns=['customer_id','top7_products_json']),on='customer_id',validate='one_to_one')
    base=base.merge(rec[['customer_id','catalog_status','scoring_method']].rename(columns={'scoring_method':'recommendation_scoring_method'}),on='customer_id',validate='one_to_one')
    base['recommendation_method']=c['recommendation_method']
    base['recommendation_eligibility']=np.where(base.catalog_status.eq('current_complete'),'current_catalog_verified','verify_current_portfolio_before_contact')
    top1=pd.DataFrame(top1,columns=['customer_id','product','catalog_status'])
    base.to_parquet(out/f'customer_analytics_{m}.parquet',index=False)
    group=base.assign(persona_group=base.persona_id.fillna('NoCurrentPersona'))
    coverage=group.groupby(['persona_group','lifecycle'],dropna=False).agg(n=('customer_id','size'),
        clv_predicted_n=('expected_acquisitions','count')).reset_index()
    coverage['clv_coverage']=coverage.clv_predicted_n/coverage.n
    coverage.to_csv(out/'coverage.csv',index=False)
    make_cards(base,top1,p['persona_dir'],out)
    sources=[]
    for path in dict.fromkeys(used):
        info=dict(path=str(path),size_bytes=path.stat().st_size)
        if path.suffix=='.json':info['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append(info)
    manifest=dict(as_of_month=m,n_known=len(base),n_observed=int(base.is_observed.sum()),
        n_persona_assigned=int(base.persona_id.notna().sum()),n_clv=int(base.expected_acquisitions.notna().sum()),
        recommendation_rows=recommendation_rows,config=c,source_files=sources,
        validation='schema, unique IDs, same month, source selection, lifecycle, persona rules, catalog and recommendation checks',
        no_model_refit=True,no_future_labels=True)
    (out/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
