import json,hashlib,io
from pathlib import Path
import pandas as pd
import argparse
parser=argparse.ArgumentParser(description='Extract aggregate evidence from ORIGINAL executed uploads, not stripped repo notebooks.')
parser.add_argument('--source-dir',required=True)
args=parser.parse_args()
R=Path(__file__).resolve().parents[1]; U=Path(args.source_dir)
files=[('santander-eda.ipynb','00_raw_eda.ipynb'),('01-r-f-m-analysis (1)(2).ipynb','01_rfm_features.ipynb'),('02-rf-rfm-combination-analysis (1)(1).ipynb','02_rfm_combinations.ipynb'),('03-rfm-quantile-333-555-1(5).ipynb','03_rfm_comparison.ipynb'),('05-lifecycle-eda-insights(2).ipynb','05_lifecycle.ipynb'),('06-affinity-rfm-lifecycle(1).ipynb','06_affinity.ipynb'),('07-clv-proxy(2).ipynb','07_clv_proxy.ipynb'),('08-persona-santander (3).ipynb','08_persona_rules.ipynb'),('09-persona-eda-alternatives (3).ipynb','09_persona_alternatives.ipynb'),('10-persona-decision-tree (2).ipynb','10_persona_tree.ipynb'),('10-persona-rfm-decision-tree(1).ipynb','10b_persona_fm_experiments.ipynb'),('11-persona-lifecycle (2).ipynb','11_persona_lifecycle.ipynb'),('12-persona-clv (1).ipynb','12_persona_clv.ipynb'),('13-persona-affinity(1).ipynb','13_persona_affinity.ipynb'),('14-persona-demographics (1).ipynb','14_persona_demographics.ipynb')]
manifest=[]
for src,dst in files:
 b=(U/src).read_bytes();n=json.loads(b)
 for i,c in enumerate(n['cells']):
  c['metadata']={};c['id']=f'cell-{i:03}'
  if c['cell_type']=='code':c['outputs']=[];c['execution_count']=None
 n['metadata']={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}}
 n['nbformat_minor']=5
 (R/'notebooks'/dst).write_text(json.dumps(n,ensure_ascii=False,indent=1),encoding='utf-8')
 manifest.append(dict(original=src,repository='notebooks/'+dst,sha256_uploaded=hashlib.sha256(b).hexdigest(),outputs_removed=True))
(R/'reports/source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
rows=[]
def extract(src,cell,out,name):
 n=json.loads((U/src).read_text());o=n['cells'][cell]['outputs'][out]
 html=''.join(o['data']['text/html']);t=pd.read_html(io.StringIO(html))[0]
 if isinstance(t.columns,pd.MultiIndex):t.columns=['_'.join(str(v) for v in x if not str(v).startswith('Unnamed')) for x in t.columns]
 t=t.loc[:,[not str(c).startswith('Unnamed') for c in t.columns]]
 target=R/'reports/evidence'/f'{name}.csv';t.to_csv(target,index=False)
 rows.append(dict(file=target.relative_to(R).as_posix(),source=src,cell_index_zero_based=cell,output_index=out,rows=len(t),precision='saved display precision; not recomputed from customer predictions',partial=bool(t.astype(str).eq('...').any().any())))
 return t
extract('03-rfm-quantile-333-555-1(5).ipynb',9,0,'rfm_scorecard')
extract('05-lifecycle-eda-insights(2).ipynb',15,0,'lifecycle_ablation')
extract('13-persona-affinity(1).ipynb',16,0,'affinity_validation')
extract('13-persona-affinity(1).ipynb',18,1,'affinity_test_summary')
extract('07-clv-proxy(2).ipynb',7,0,'clv_validation_selection')
# all saved CLV summary tables located by immediately preceding printed header
n=json.loads((U/'07-clv-proxy(2).ipynb').read_text());prev='';j=0
for oi,o in enumerate(n['cells'][9]['outputs']):
 txt=''.join(o.get('text',[]))
 if txt:prev=txt.strip()
 if o.get('data',{}).get('text/html'):
  if prev.startswith('TEST 1m / acquisitions:'):extract('07-clv-proxy(2).ipynb',9,oi,'clv_test_acquisitions_1m')
  if prev.startswith('PHƯƠNG PHÁP KHÓA'):extract('07-clv-proxy(2).ipynb',9,oi,'clv_selected_test_monthly')
  prev=''
extract('10-persona-decision-tree (2).ipynb',7,1,'persona_behavior_latest')
extract('12-persona-clv (1).ipynb',3,0,'persona_clv_coverage_latest')
extract('12-persona-clv (1).ipynb',3,1,'persona_clv_distribution_latest')
extract('13-persona-affinity(1).ipynb',26,1,'persona_temporal_rules')
extract('10-persona-decision-tree (2).ipynb',12,1,'persona_rfm_ablation')
extract('14-persona-demographics (1).ipynb',5,0,'demographics_join_coverage')
extract('14-persona-demographics (1).ipynb',7,0,'demographics_numeric_latest')
extract('14-persona-demographics (1).ipynb',7,1,'demographics_quality_latest')
extract('14-persona-demographics (1).ipynb',9,1,'demographics_numeric_stability')
extract('14-persona-demographics (1).ipynb',11,0,'demographics_profiles_latest')
(R/'reports/evidence_manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(r['file'],r['rows'],'partial',r['partial'])
