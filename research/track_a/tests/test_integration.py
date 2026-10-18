"""Synthetic integration checks, not a rerun of Santander metrics."""
import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from santander_wrap.build import build
from santander_wrap.schema import PRODUCTS

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name);m='2016-05';self.m=m
        keys=['rfm_features_dir','rfm_model_dir','lifecycle_dir','persona_dir','clv_dir','affinity_dir','snapshot_cache_dir']
        p={k:root/k for k in keys}
        for d in p.values():d.mkdir()
        p['output_dir']=root/'out';p['raw_csv_or_zip']=root/'train_ver2.csv';self.p=p
        self.c=dict(as_of_month=m,rfm_method='Hybrid_REDA_F4_M5',rfm_fit_month='2015-11',clv_horizon_months=1,
            clv_target='acquisitions',clv_method='ML_RFM_stable',recommendation_method='recent3_temporal',
            lifecycle_rule_version='lifecycle-v3-presence-gap6',persona_version='tree6-nov2015-v1',paths={k:str(v) for k,v in p.items()})
        ids=list(range(1,11))
        self.life=pd.DataFrame(dict(customer_id=ids,month=m,is_observed=[True]*8+[False]*2,
            lifecycle=['Active']*8+['At-risk','Churned'],missing_months=[0]*8+[2,6],rule_version=self.c['lifecycle_rule_version']))
        self.life.to_parquet(p['lifecycle_dir']/f'lifecycle_{m}.parquet',index=False)
        ns=[1,3,2,1,3,5,0,np.nan];fs=[0,0,1,2,3,2,0,0]
        pd.DataFrame(dict(customer_id=range(1,9),month_idx=2016*12+5,R=[np.nan,np.nan,1,0,2,1,np.nan,np.nan],F_event_months=fs,F_events=fs,
            M_group_points=[1,4,10,20,30,40,0,np.nan],M_n_products=ns,products_complete=[True]*7+[False])).to_parquet(p['rfm_features_dir']/f'rfm_{m}.parquet',index=False)
        self.js(p['rfm_model_dir']/'config.json',{'fit_month':'2015-11'})
        self.js(p['rfm_model_dir']/'bucket_specs.json',{'Hybrid_REDA_F4_M5':{'R':[-np.inf,0,2,7,np.inf],
            'F_event_months':[-np.inf,1,2,4,np.inf],'M_group_points':[-np.inf,2,5,15,35,np.inf]}})
        ps=pd.DataFrame(dict(customer_id=range(1,7),as_of_month=m,persona_id=[f'P{i}' for i in range(1,7)],valid_pairs=[5]*6))
        ps.to_parquet(p['persona_dir']/f'personas_tree_{m}.parquet',index=False)
        self.js(p['persona_dir']/'config.json',{'version':self.c['persona_version'],'USE_M':False,'fit_label_month':'2015-12'})
        pd.DataFrame({'persona_id':ps.persona_id,'month':'2016-04','rate':[.01,.03,.07,.25,.15,.12]}).to_csv(p['persona_dir']/'persona_validation_monthly.csv',index=False)
        pd.DataFrame(dict(ncodpers=range(1,9),fecha_dato=m+'-28',age=[15,164,40,35,42,46,25,30],
            renta=[np.nan,100000,90000,80000,100000,120000,50000,60000],antiguedad=[3,100,-999999,20,50,120,2,1],
            canal_entrada='KAT',segmento='02 - PARTICULARES',sexo='V',nomprov='MADRID')).to_csv(p['raw_csv_or_zip'],index=False)
        snap=pd.DataFrame(0,index=range(7),columns=PRODUCTS,dtype='uint8');snap.insert(0,'customer_id',range(1,8))
        for i,n in enumerate(ns[:7]):snap.loc[i,PRODUCTS[:int(n)]]=1
        snap.to_parquet(p['snapshot_cache_dir']/f'{m}.parquet',index=False)
        selection={'selected_by_horizon':{'1':{'acquisitions':'ML_RFM_stable'}}}
        for name in ['selection.json','config.json']:self.js(p['clv_dir']/name,selection)
        pd.DataFrame(dict(customer_id=range(1,8),as_of_month=m,horizon_months=1,predicted_acquisitions=[.01,.02,.1,.5,.3,.2,.03],
            method_acquisitions='ML_RFM_stable',lifecycle='Active',rfm_cluster='SOURCE_F3')).to_parquet(p['clv_dir']/f'clv_predictions_{m}_1m.parquet',index=False)
        self.js(p['affinity_dir']/'selection.json',{'selected_method':'recent3_temporal','validation_month':'2015-12','window':3})
        folder=p['affinity_dir']/'product_recommendation'/m/'recent3_temporal';folder.mkdir(parents=True);self.rec=folder/'part_0000000.parquet'
        rows=[];statuses=[]
        for i in ids:
            count=int(ns[i-1]) if i<=7 else 0
            rows.append(dict(customer_id=i,as_of_month=m,method='recent3_temporal',products=PRODUCTS[count:count+7],ranking_scores=list(map(float,range(7,0,-1)))))
            statuses.append(dict(customer_id=i,catalog_status='current_complete' if i<=7 else 'last_complete_snapshot',scoring_method='recent3_temporal' if i<=7 else 'popularity_fallback'))
        pd.DataFrame(rows).to_parquet(self.rec,index=False);pd.DataFrame(statuses).to_parquet(folder/'status_0000000.parquet',index=False)
    @staticmethod
    def js(p,d):p.write_text(json.dumps(d))
    def run_build(self):return build(copy.deepcopy(self.c))
    def test_full_build(self):
        r=self.run_build();self.assertEqual(r['n_known'],10);self.assertEqual(r['n_clv'],7)
        d=pd.read_parquet(self.p['output_dir']/f'customer_analytics_{self.m}.parquet').set_index('customer_id')
        self.assertEqual(d.loc[1,'age'],15);self.assertTrue(pd.isna(d.loc[2,'age']))
        self.assertTrue(pd.isna(d.loc[1,'renta']));self.assertTrue(pd.isna(d.loc[3,'antiguedad']))
        self.assertTrue(d.loc[[9,10],'expected_acquisitions'].isna().all());self.assertTrue(d.loc[[7,8,9,10],'persona_id'].isna().all())
        self.assertTrue(pd.isna(d.loc[9,'age']));self.assertEqual(d.loc[9,'recommendation_eligibility'],'verify_current_portfolio_before_contact')
        self.assertEqual(d.loc[6,'clv_source_rfm_cluster'],'SOURCE_F3');self.assertEqual(d.loc[6,'rfm_method'],'Hybrid_REDA_F4_M5')
        self.assertTrue(pd.isna(d.loc[1,'rfm_cluster']))
        rec=pd.read_parquet(self.p['output_dir']/f'recommendations_{self.m}');self.assertEqual(len(rec),70)
        self.assertTrue((self.p['output_dir']/'persona_cards.md').is_file())
    def test_owned_product_rejected(self):
        d=pd.read_parquet(self.rec);d.at[0,'products']=np.array([PRODUCTS[0]]+PRODUCTS[2:8]);d.to_parquet(self.rec,index=False)
        with self.assertRaisesRegex(ValueError,'owned product'):self.run_build()
    def test_wrong_month_rejected(self):
        p=self.p['persona_dir']/f'personas_tree_{self.m}.parquet';d=pd.read_parquet(p);d['as_of_month']='2016-04';d.to_parquet(p,index=False)
        with self.assertRaisesRegex(ValueError,'wrong or missing'):self.run_build()
    def test_duplicate_id_rejected(self):
        pd.concat([self.life,self.life.iloc[:1]],ignore_index=True).to_parquet(self.p['lifecycle_dir']/f'lifecycle_{self.m}.parquet',index=False)
        with self.assertRaisesRegex(ValueError,'duplicate'):self.run_build()
    def test_clv_selection_rejected(self):
        self.js(self.p['clv_dir']/'selection.json',{'selected_by_horizon':{'1':{'acquisitions':'ML_full'}}})
        with self.assertRaisesRegex(ValueError,'validation selection'):self.run_build()
    def test_persona_rules_rejected(self):
        p=self.p['persona_dir']/f'personas_tree_{self.m}.parquet';d=pd.read_parquet(p);d.loc[0,'persona_id']='P2';d.to_parquet(p,index=False)
        with self.assertRaisesRegex(ValueError,'rules mismatch'):self.run_build()
    def test_future_history_rejected(self):
        pd.DataFrame({'persona_id':[f'P{i}' for i in range(1,7)],'month':'2016-05','rate':.05}).to_csv(self.p['persona_dir']/'persona_validation_monthly.csv',index=False)
        with self.assertRaisesRegex(ValueError,'precede current'):self.run_build()
    def test_duplicate_recommendations_rejected(self):
        d=pd.read_parquet(self.rec);d.at[0,'products']=np.array([PRODUCTS[1]]*7);d.to_parquet(self.rec,index=False)
        with self.assertRaisesRegex(ValueError,'duplicates'):self.run_build()

if __name__=='__main__':unittest.main()
