"""Render persona cards from observed summaries or validated full integration."""
from pathlib import Path
import pandas as pd
from .demographics import NUMERIC
from .schema import require

RULES={
'P1':'F_event_months = 0; n_products <= 2',
'P2':'F_event_months = 0; n_products >= 3',
'P3':'F_event_months = 1',
'P4':'F_event_months >= 2; n_products <= 1',
'P5':'F_event_months >= 2; 2 <= n_products <= 4',
'P6':'F_event_months >= 2; n_products >= 5'}
ACTIONS={
'P1':'Tiếp cận chi phí thấp theo nhu cầu; dùng CLV-proxy để ưu tiên trong nhóm, affinity để chọn sản phẩm.',
'P2':'Xác minh nhu cầu bổ sung ở khách lâu năm; chưa quan sát acquisition không đồng nghĩa không sử dụng.',
'P3':'Theo dõi khả năng mở tiếp; dùng R và CLV-proxy để phân biệt trong nhóm.',
'P4':'Kiểm tra đóng/mở lại trước khi gọi là tăng trưởng; chưa suy ra churn hay lợi nhuận.',
'P5':'Ứng viên thử bán chéo sản phẩm chưa sở hữu, kiểm tra bằng thử nghiệm khi có dữ liệu triển khai.',
'P6':'Tìm khoảng trống danh mục; không mặc định nhóm này luôn có xác suất mua cao nhất.'}
DESCRIPTIONS={
'P1':'Danh mục cơ bản, chưa quan sát event; tuổi trung vị thấp hơn baseline.',
'P2':'Danh mục đa sản phẩm, chưa quan sát event; khách lâu năm và lớn tuổi hơn mặt bằng.',
'P3':'Một tháng acquisition được quan sát; demographics khá đa dạng.',
'P4':'Acquisition lặp lại, danh mục hẹp; thâm niên tương đối ngắn.',
'P5':'Acquisition lặp lại, danh mục 2–4 sản phẩm; demographics gần mặt bằng hơn P2/P6.',
'P6':'Acquisition lặp lại, danh mục rộng; khách lâu năm và lớn tuổi hơn mặt bằng.'}


def pct(x):return f'{x:.2%}'


def make_evidence_cards(repo):
    repo=Path(repo);e=repo/'reports/evidence'
    behavior=pd.read_csv(e/'persona_behavior_latest.csv').set_index('persona_id')
    demo=pd.read_csv(e/'demographics_profiles_latest.csv').set_index('persona_id')
    numeric=pd.read_csv(e/'demographics_numeric_latest.csv')
    stability=pd.read_csv(e/'demographics_numeric_stability.csv')
    clv=pd.read_csv(e/'persona_clv_distribution_latest.csv')
    coverage=pd.read_csv(e/'persona_clv_coverage_latest.csv')
    affinity=pd.read_csv(e/'persona_temporal_rules.csv')
    cards=[]
    for pid,b in behavior.iterrows():
        d=demo.loc[pid]
        require(int(b.n)==int(d.n),f'evidence persona/demographics n mismatch for {pid}')
        lines=[f'# {pid} — {b.persona_name}', '', DESCRIPTIONS[pid], '',
            '**Nguồn:** output notebook 10 và 14 đã chạy, snapshot 2016-05. Số liệu lấy từ bảng hiển thị được lưu; không tái tính từ raw.', '',
            f'- Rule: `{b.rule}`; chỉ áp dụng trên cohort persona đủ điều kiện upstream.',
            f'- Quy mô: {int(b.n):,} khách; {pct(b.share_eligible)} cohort persona; {pct(b.share_known)} known population.',
            f'- F trung vị: {b.F_median:g} tháng có event; số sản phẩm trung vị: {b.products_median:g}.',
            f'- Acquisition t+1 trong development (source 2015-12–2016-04): **{pct(b.historical_rate_min)} - {pct(b.historical_rate_max)}**.',
            '  Đây là min–max tỷ lệ nhóm qua tháng, không phải khoảng xác suất cá nhân hay CI.', '',
            '| Thuộc tính | Median | Q25 - Q75 | Coverage | Median baseline |',
            '|---|---:|---:|---:|---:|']
        for f in NUMERIC:
            r=numeric.loc[numeric.persona_id.eq(pid)&numeric.feature.eq(f)].iloc[0]
            lines.append(f'| {f} | {r["median"]:,.1f} | {r.q25:,.1f} - {r.q75:,.1f} | {pct(r.valid_share)} | {r.baseline_median:,.1f} |')
        lines+=['','Thu nhập chỉ mô tả khách có renta hợp lệ; chưa phải giá trị tiền tạo cho ngân hàng.', '', '**Profile ổn định qua 6 tháng:**']
        for f in ['age','antiguedad']:
            r=stability.loc[stability.persona_id.eq(pid)&stability.feature.eq(f)].iloc[0]
            lines.append(f'- {f}: trung vị từng tháng trong khoảng {r.median_min:g} - {r.median_max:g}; không chứng minh cùng khách giữ nguyên persona.')
        for f in ['canal_entrada','nomprov']:
            lines.append(f'- Top {f} tại tháng cuối: {d[f]}.')
        forecasts=clv.loc[clv.persona_group.eq(pid)]
        cover=coverage.loc[coverage.persona_group.eq(pid)]
        require(int(forecasts.n.sum())==int(b.n),f'CLV/persona evidence population mismatch: {pid}')
        forecast_mean=(forecasts.n*forecasts['mean']).sum()/forecasts.n.sum()
        lines+=['', '**Dự báo và trạng thái hiện tại (nguồn notebook 12):**',
            f'- Mean CLV-proxy 1 tháng ≈ **{forecast_mean:.6f}**; coverage {pct(cover.predicted_n.sum()/cover.known_n.sum())}; method ML_RFM_stable.',
            '  Output nguồn là points; mọi product weight=1 nên cùng đơn vị số acquisition. Mean gộp theo n từ các nhóm lifecycle; không gộp median bằng trung bình.',
            '- Lifecycle: '+ '; '.join(f'{r.lifecycle}: {int(r.known_n):,}' for r in cover.itertuples())+'.',
            '  Forecast chưa có nhãn tương lai để xác minh; lifecycle chỉ là presence proxy.',
            '', '**Ví dụ quan hệ sản phẩm lịch sử (nguồn 13, nhánh persona affinity):**',
            '| Đang có A, chưa có B → mở B tháng sau | Exposure khách-tháng | Acquisitions | Confidence quan sát |',
            '|---|---:|---:|---:|']
        for r in affinity.loc[affinity['group'].eq(pid)].head(2).itertuples():
            lines.append(f'| {r.A} → {r.B} | {int(r.exposure):,} | {int(r.acquisitions):,} | {pct(r.confidence)} |')
        lines+=['', 'Các luật trên được hiển thị theo lift, là mô tả lịch sử có support; không phải top-7 cuối hoặc tác động nhân quả. Export chính vẫn dùng recent3_temporal đã khóa.',
            '', '**Cách dùng kết quả:**',f'- {ACTIONS[pid]}',
            '- CLV-proxy ưu tiên khách, affinity chọn sản phẩm; chưa có top-7 customer-level để tổng hợp tần suất gợi ý thật.',
            '- RFM là tag chi tiết; nhãn F4 cuối và nhãn nguồn CLV được phân biệt trong bảng tổng hợp.',
            '', '**Giới hạn:** F=0 là chưa quan sát event trong lịch sử dataset; card là mô tả, không thêm mô hình dự đoán.']
        text='\n'.join(lines)+'\n';(repo/'docs/personas'/f'{pid}.md').write_text(text,encoding='utf-8');cards.append(text)
    (repo/'docs/04_persona_cards.md').write_text('# Sáu persona card — evidence snapshot 2016-05\n\n'+'\n---\n\n'.join(cards),encoding='utf-8')


def make_cards(master,top1,persona_dir,out):
    """Rerender cards with actual CLV and recommendation summaries on Kaggle."""
    assigned=master.loc[master.persona_id.notna()];stats=[];cards=[]
    history_path=Path(persona_dir)/'persona_validation_monthly.csv'
    require(history_path.is_file(),f'Missing {history_path}')
    history=pd.read_csv(history_path)
    month=master.as_of_month.iloc[0]
    require(history.month.astype(str).lt(month).all(),'historical validation must precede current forecast month')
    rec=top1.merge(master[['customer_id','persona_id']],on='customer_id',validate='one_to_one')
    rec=rec.loc[rec.catalog_status.eq('current_complete') & rec.persona_id.notna()]
    top_counts=rec.groupby(['persona_id','product']).size().rename('customer_n').reset_index()
    top_counts['share_top1_within_persona']=top_counts.customer_n/top_counts.persona_id.map(rec.persona_id.value_counts())
    top_counts.to_csv(out/'persona_recommendation_top1.csv',index=False)
    for pid,g in assigned.groupby('persona_id'):
        z=history.loc[history.persona_id.eq(pid)]
        require(len(z)>0,f'No acquisition history for {pid}')
        lines=[f'# {pid}', '', f'- Tháng: {month}; rule: `{RULES[pid]}`.',
            f'- Quy mô: {len(g):,}; {pct(len(g)/len(assigned))} assigned; {pct(len(g)/len(master))} known.',
            f'- Acquisition t+1 lịch sử: {pct(z.rate.min())} - {pct(z.rate.max())}; min–max qua tháng development, không phải forecast.',
            f'- Hành động giả thuyết: {ACTIONS[pid]}', '', '| Biến | Median | Q25 - Q75 | Coverage |','|---|---:|---:|---:|']
        row=dict(persona_id=pid,n=len(g),share_assigned=len(g)/len(assigned))
        for f in NUMERIC:
            v=g[f].dropna();row[f+'_median']=v.median();row[f+'_coverage']=len(v)/len(g)
            lines.append(f'| {f} | {v.median():,.1f} | {v.quantile(.25):,.1f} - {v.quantile(.75):,.1f} | {pct(len(v)/len(g))} |')
        predictions=g.expected_acquisitions.dropna()
        row.update(clv_n=len(predictions),expected_acquisitions_mean=predictions.mean(),expected_acquisitions_median=predictions.median())
        lines+=['', f'- CLV-proxy 1 tháng: mean={predictions.mean():.4f}; median={predictions.median():.4f}; coverage={pct(len(predictions)/len(g))}. Đây là số acquisition kỳ vọng, không phải tiền.',
            '- RFM method: '+str(g.rfm_method.iloc[0])+'. CLV giữ nguyên method/nhãn nguồn, không refit theo nhóm mới.',
            '- Cơ cấu lifecycle: '+ '; '.join(f'{s}: {pct(n/len(g))}' for s,n in g.lifecycle.value_counts().items())+'.']
        top=top_counts.loc[top_counts.persona_id.eq(pid)].nlargest(3,'customer_n')
        lines.append('- Sản phẩm thường đứng top-1 trong đề xuất: '+('; '.join(f'{r.product}: {pct(r.share_top1_within_persona)}' for r in top.itertuples()) or 'Không có đề xuất current verified')+'.')
        lines.append('  Đây là tần suất được gợi ý, không phải tần suất mua hay xác suất chuyển đổi.')
        cards.append('\n'.join(lines));stats.append(row)
    pd.DataFrame(stats).to_csv(out/'persona_summary.csv',index=False)
    (out/'persona_cards.md').write_text('# Persona cards tổng hợp\n\n'+'\n\n---\n\n'.join(cards)+'\n',encoding='utf-8')
