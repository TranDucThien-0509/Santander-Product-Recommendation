"""Render a report from saved aggregate evidence; never rank across different cohorts."""
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];E=R/'reports/evidence'

def table(df):
    def fmt(x):
        if pd.isna(x):return 'NA'
        if isinstance(x,float):return f'{x:.6f}'
        return str(x).replace('|','/')
    return '\n'.join(['| '+' | '.join(map(str,df.columns))+' |','|'+'|'.join(['---']*len(df.columns))+'|']+
                     ['| '+' | '.join(fmt(x) for x in row)+' |' for row in df.itertuples(index=False,name=None)])
rfm=pd.read_csv(E/'rfm_scorecard.csv')
rfm=rfm.loc[rfm.method.isin(['Quantile_555','Hybrid_REDA_F3_M5','Hybrid_REDA_F4_M5','KMeans_6','M_only']),['method','AP','Lift10','Brier','rank_stability_min']]
clv=pd.read_csv(E/'clv_test_acquisitions_1m.csv')
clv=clv.loc[clv.method.isin(['ML_RFM_stable','ML_RFM','ML_RFM_only','BGNBD','has_event_mean']),['method','RMSE','capture10','lift10','calibration_ratio']]
aff=pd.read_csv(E/'affinity_test_summary.csv')
aff=aff.loc[aff.method.isin(['recent3_temporal','temporal','popularity','apriori','item2vec','blend80']),['method','MAP7_all','recall7_acquirers']]
life=pd.read_csv(E/'lifecycle_ablation.csv')
persona=pd.read_csv(E/'persona_rfm_ablation.csv')[['method','AP_mean','Lift10_mean','Brier_mean']]
selected=pd.read_csv(E/'clv_selected_test_monthly.csv')
selected=selected.loc[selected.horizon.eq(1)&selected.target.eq('acquisitions')]
text='''# Bước 2 — Benchmark tổng hợp từ output đã lưu

Số liệu trích từ HTML tables trong notebook upload, ở độ chính xác hiển thị, không tính lại metric từ customer-level predictions. Provenance từng bảng: [evidence manifest](../reports/evidence_manifest.json). Tất cả tháng đều là **tháng nguồn**; nhãn acquisition t+1 nằm ở tháng sau.

## RFM — HasEvent, cặp source Dec2015–Apr2016

Trung bình đều metric từng tháng. Cohort này có baseline acquisition khoảng 12.12%, khác cohort tất cả khách của CLV/persona. Không so Lift10 trực tiếp giữa hai cohort.

'''+table(rfm)+'''

Chọn F4 cho tag mô tả cuối và bàn giao. M_only có AP cao hơn nhưng ranking đơn biến không thay vai trò phân khúc R/F/M; không tuyên bố F4 thắng mọi baseline. Rank stability đo thứ tự rate nhóm, không đo membership.

## Persona + RFM — cohort persona đủ history, cùng labels

'''+table(persona)+'''

Đây là refinement score, không tạo thêm persona mới. P1–P6 vẫn là sáu nhóm gốc. Các kết quả đã được khảo sát trong development, chưa phải holdout mới.

## Lifecycle ablation — HasEvent đủ RFM và nhãn

'''+table(life)+'''

Increment nhỏ; dùng lifecycle chủ yếu cho presence, eligibility và theo dõi quay lại. New/Win-back không đủ support để suy ra mọi tổ hợp đều hữu ích. Chưa có bằng chứng retention intervention hiệu quả.

## Acquisition-proxy — toàn current complete có nhãn, horizon 1m

Validation source Nov2015; method ranking khóa **ML_RFM_stable**. Test source Dec2015–Apr2016, rolling refit bằng nhãn đã hoàn tất. Số dưới đây là trung bình đều từng tháng, không pooled metric.

'''+table(clv)+'''

`capture10` là tỷ trọng tổng product acquisitions ở top10% khách; `lift10` chia cho tỷ trọng được chọn. Không phải số khách mua / toàn bộ khách mua. Calibration ratio = tổng forecast / tổng actual mỗi tháng; mean của ratio không phải pooled ratio.

BG/NBD gồm fallback cho phần lớn khách. Dù ML_RFM tốt hơn trên một số metric test, giữ method đã chọn ở validation.

### Method đã khóa theo tháng

'''+table(selected[['month','method','capture10','RMSE','calibration_ratio']])+'''

## Affinity — toàn cặp snapshot đầy đủ, test Jan–Apr2016

Validation source Dec2015 chọn **recent3_temporal**, window3. Main MAP@7 có cả khách không mở sản phẩm (AP=0). Recall dưới đây chỉ trên acquirers; không nhầm mẫu số.

'''+table(aff)+'''

Test cho thấy recent3_temporal thấp hơn temporal dù thắng validation. Báo trung thực kết quả này; không chọn blend80 sau khi xem test. Thử nghiệm item2vec có kết quả thấp trong cấu hình hiện tại, không chứng minh mọi embedding đều kém.

## Phân biệt evidence và forecast

- Snapshot 2016-05 chưa có labels sản phẩm 2016-06 trong bộ train. Current score không phải kết quả test đã xác minh.
- Horizon 3/6m giữ trong notebook 07 để phân tích phụ; không gộp vào bảng 1m.
- Card dùng demographics May2016 và acquisition rate range của nguồn Dec2015–Apr2016; không gọi range lịch sử là forecast May.
- Các bộ phương pháp khác cohort/target/horizon không tạo một bảng xếp hạng chung.
'''
(R/'docs/02_benchmarks.md').write_text(text,encoding='utf-8')
rows=[]
for comp,df,cohort,period in [('RFM',rfm,'HasEvent valid RFM pairs','2015-12..2016-04'),
 ('Persona',persona,'assigned valid persona pairs','2015-12..2016-04'),
 ('Lifecycle',life,'HasEvent RFM valid pairs','2015-12..2016-04'),
 ('CLV',clv,'current complete, fully observed next-month pairs','2015-12..2016-04'),
 ('Affinity',aff,'all complete next-month pairs','2016-01..2016-04')]:
 for record in df.to_dict('records'):
  method=record.pop('method')
  for metric,value in record.items():rows.append(dict(component=comp,method=method,metric=metric,value=value,cohort=cohort,source_months=period,evidence='saved_display_aggregate'))
pd.DataFrame(rows).to_csv(R/'reports/benchmark_summary.csv',index=False)
print('Rendered benchmarks.')
