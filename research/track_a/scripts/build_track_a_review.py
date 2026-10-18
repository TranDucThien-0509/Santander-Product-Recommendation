"""Build and optionally execute the 15–20 minute aggregate-only Track A review."""
import argparse
from pathlib import Path
import nbformat


def build(root):
    cells = []
    def md(source):
        cells.append(nbformat.v4.new_markdown_cell(source))
    def code(source):
        cells.append(nbformat.v4.new_code_cell(source))

    md("""# Track A — Customer Segmentation: RFM, CLV, Affinity, Persona
**Demo 18 phút.** Research sample cố định 10.000 khách, 17 tháng; full-cloud recommendation và evidence notebook gốc là các phạm vi khác.

Agenda: dữ liệu/EDA (3′) → event/lifecycle (2′) → RFM (2′) → CLV/SHAP (4′) → affinity (2′) → persona (3′) → handoff/giới hạn (2′).
Notebook chỉ đọc aggregate có sẵn trong GitHub; không cần raw Kaggle, credential, model pickle hoặc MLflow server để Run All.""")
    code("""from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
%matplotlib inline
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents]
            if (p / 'research/track_a/reports/sample_10k/summary.json').is_file())
REP = ROOT / 'research/track_a/reports/sample_10k'
summary = json.loads((REP / 'summary.json').read_text(encoding='utf-8'))
completed = json.loads((REP / 'completed.json').read_text(encoding='utf-8'))
assert completed['status'] == 'success'
assert summary['eda']['customers'] == 10000
display(pd.DataFrame([summary['eda']]).drop(columns=['cardinality','missing_share','absent_optional_columns']))""")
    md("""## 1. Snapshot không phải transaction — EDA (3 phút)
Một dòng = một khách ở một tháng, 24 cờ ownership. Renta không phải số tiền giao dịch; panel absence không chứng minh rời ngân hàng. File raw đang dùng ở full pipeline khoảng 2,3 GB, không mặc định con số ~13 GB trong brief.

8 finding dưới đây được tính lại từ sample; các vấn đề của notebook EDA lịch sử được ghi trong limitations.md.""")
    code("""report = (REP / 'TRACK_A_REPORT.md').read_text(encoding='utf-8')
display(Markdown(report.split('## EDA')[1].split('## CLV')[0]))
display(pd.read_csv(REP / 'raw_column_audit.csv'))
monthly = pd.read_csv(REP / 'monthly_snapshots.csv')
monthly.plot(x='month', y='snapshots', marker='o', rot=60, title='Sample snapshots theo tháng', figsize=(9,3))
plt.show()""")
    md("""## 2. Acquisition event và lifecycle (2 phút)
Chỉ tính 0→1 trên hai tháng **liền kề và đủ 24 flag**, một dòng/product acquired. Nhiều sản phẩm trong một tháng vẫn chỉ một event-month cho BG/NBD/RFM F.

Giữ lifecycle presence của v2; lớp export bổ sung activity/death. Deceased → Churned/ineligible, inactive observed → At-risk trừ New/Win-back, thiếu status không tự thành eligible. Cohort và quy tắc trong feature spec.""")
    code("""display(pd.DataFrame([summary['events']]))
display(pd.DataFrame(summary['lifecycle'].items(), columns=['lifecycle','customers']))
display(pd.read_csv(REP / 'panel_presence.csv'))""")
    md("""## 3. RFM: quantile / KMeans / rule (2 phút)
R = months since last observed acquisition, F = event-month count, M dùng current product count cho tiering. Portfolio propensity points trong ranker là feature khác, không phải monetary thật.

Fit cutoff 2015-11, giữ edges/scaler/centers cố định; duplicate quantiles được collapse. ARI và stay rate chỉ đo trên khách chung hai tháng, báo cả coverage. AP/Lift/Brier gốc nằm trong docs/02_benchmarks.md và không trộn cohort với bảng mới.""")
    code("""display(pd.read_csv(REP / 'rfm_geometry.csv').groupby('method')[['groups','silhouette']].mean())
rfm = pd.read_csv(REP / 'rfm_membership_stability.csv')
display(rfm.groupby('method')[['common_coverage','same_label_rate','adjusted_rand']].mean())""")
    md("""## 4. CLV-proxy 6 tháng: xác suất vs boosting (3 phút)
Cutoff 2015-11 → label end 2016-05. Train origins 03–05/2015, chỉ nhãn hoàn tất ≤ cutoff. Cùng cohort liên tục được quan sát, thiếu một cặp thì censored.

BG/NBD frequency = repeat events, recency = last-first event, T = cutoff-first event; khác RFM R. Gamma-Gamma dùng acquisitions/event-month làm value proxy, không phải money. Khách không đủ history dùng mean fallback, không gọi điểm toàn cohort là BG/NBD thuần.

Config 6m cố định, không có model selection qua validation 6m. Capture10 chia công bằng tie bằng expected fractional selection.""")
    code("""audit = json.loads((REP / 'clv_6m_audit.json').read_text())
assert audit['max_train_label_month'] <= audit['origin']
display(pd.DataFrame([{k:audit[k] for k in ['origin','label_end','train_rows','max_train_label_month','label_coverage']}]))
display(pd.read_csv(REP / 'clv_6m_benchmark.csv'))
display(pd.read_csv(REP / 'clv_probabilistic_fit_status.csv'))
errors = pd.read_csv(REP / 'clv_6m_segment_errors.csv')
display(errors.loc[errors.group_type.isin(['event_history','history_short'])])""")
    md("""### SHAP — giải thích model, không phải causal effect (1 phút)
Mean absolute SHAP trên 200 khách; additive reconstruction đã được kiểm tra với prediction thật của model. Poisson model có link log kỳ vọng acquisitions, không diễn giải raw SHAP là số tiền hoặc trực tiếp là delta acquisition.""")
    code("""assert audit['explanation']['additive_reconstruction_verified']
importance = pd.read_csv(REP / 'clv_6m_shap_importance.csv')
display(importance)
importance.sort_values('mean_abs_shap').plot.barh(x='feature', y='mean_abs_shap', legend=False,
    title='CLV 6m: mean |SHAP|, log expected acquisitions', figsize=(8,3))
plt.show()""")
    md("""## 5. Affinity và next-product quality (2 phút)
Ma trận 24×24 có counts, support, confidence và lift. Bảng tháng cuối là mô tả; next-month benchmark fit ở origin và chấm ở tháng sau, mask sản phẩm đã có.

Notebook 06 gốc có Apriori itemsets đến 3 và item2vec SGNS, cùng benchmark được giữ trong docs/02_benchmarks.md. Kết quả item2vec cấu hình gốc thấp; không che kết quả đó hoặc gọi co-occurrence SVD là item2vec.""")
    code("""display(pd.read_csv(REP / 'affinity_next_month_benchmark.csv'))
rules = pd.read_csv(REP / 'affinity_pair_rules.csv')
display(rules.sort_values(['lift','count'], ascending=False).head(10))
matrix = pd.read_csv(REP / 'affinity_support_24x24.csv', index_col=0)
fig, ax = plt.subplots(figsize=(7,4))
image = ax.imshow(matrix, cmap='Blues')
ax.set_title('Co-ownership support, 24 products, latest snapshot')
fig.colorbar(image, ax=ax)
plt.show()""")
    md("""## 6. Persona có diễn giải và kiểm tra stability (3 phút)
Nghiên cứu gốc có 6 card P1–P6 theo rule với số đo/provenance đầy đủ. Phương án mới C1–Ck gom cả RFM, CLV, portfolio, affinity, age/renta/tenure, canal và segmento.

Chọn k=5…8 bằng fit-only silhouette và min-share ≥1%, không dùng acquisition labels để chọn k. Bootstrap ARI và temporal ARI/stay rate được báo riêng; mean profile ổn định không chứng minh membership ổn định. Business action vẫn là giả thuyết cần A/B test.""")
    code("""display(pd.read_csv(REP / 'persona_k_selection.csv'))
display(pd.read_csv(REP / 'persona_cluster_profiles.csv'))
display(pd.read_csv(REP / 'persona_bootstrap_stability.csv'))
display(pd.read_csv(REP / 'persona_temporal_stability.csv'))
display(Markdown((REP / 'persona_cluster_cards.md').read_text(encoding='utf-8')))""")
    md("""## 7. Feature spec, reproducibility và storage (1 phút)
Entity customer_id, grain customer/month, snake_case, source versions, actual availability và TTL 45 ngày tối đa/invalidate on next snapshot. Không join label tương lai vào feature, không carry-forward qua panel absence.

Processed customer table/event partitions không đưa lên GitHub. Chủ repo đã chọn **GCS thay AWS S3**; đây là sai khác so với brief. `processed_manifest.json` giữ file list/size/SHA256; GCS publisher tải lại kiểm hash và publish manifest cuối, không đổi IAM/ACL. Xem docs/GCS_STORAGE.md và receipt public (metadata, không chứa customer rows).

MLflow experiment `santander-track-a`; log aggregate, không log raw hoặc customer-level records.""")
    code("""spec = json.loads((REP / 'feature_store_spec.json').read_text())
display(pd.DataFrame(spec['schema']).head(20))
display(pd.DataFrame([{'view':spec['feature_view'], 'ttl':spec['ttl'], 'refresh':spec['refresh'],
    'mlflow_experiment_id':completed['mlflow']['experiment_id'],
    'mlflow_parent_run':completed['mlflow']['parent_run_id']}]))
storage = json.loads((REP / 'gcs_storage_receipt.json').read_text())
assert storage['status'] == 'verified'
display(pd.DataFrame([{k:storage[k] for k in ['provider','status','destination','file_count','data_bytes']}]))""")
    md("""## 8. Kết luận và giới hạn (1 phút)
- RFM/CLV là proxy khi không có transaction hoặc monetary thật; không dùng từ lợi nhuận đã đo.
- 6m có một development backtest với cấu hình cố định, chưa là validation độc lập/holdout. 12m chưa đủ lịch sử cho supervised train/validation/test đáng tin.
- BG/NBD/Gamma-Gamma dựa trên giả định retail; phần lớn cohort dùng fallback. Catalog hữu hạn/reopen/thời gian tháng là giới hạn.
- Selection bias do cần future complete pairs; cluster stability không phải marketing uplift.
- Storage dùng GCS theo xác nhận chủ repo, có receipt kiểm hash; **khác yêu cầu AWS S3**, không ghi thành S3 đã hoàn tất.

**Tài liệu hội đồng:** [đối chiếu track](../docs/TRACK_A_AUDIT.md), [report](../reports/sample_10k/TRACK_A_REPORT.md), [6 persona rule cards](../docs/04_persona_cards.md), [feature spec](../docs/FEATURE_STORE_SPEC.md), [cách chạy lại](../docs/REPRODUCE.md).""")
    for index, cell in enumerate(cells):
        cell.id = f"track-a-review-{index:02d}"
    notebook = nbformat.v4.new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}})
    nbformat.validate(notebook)
    return notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--kernel-name", default="python3")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    notebook = build(root)
    if args.execute:
        from nbclient import NotebookClient
        NotebookClient(notebook, timeout=120, kernel_name=args.kernel_name,
            resources={"metadata": {"path": str(root)}}).execute()
    output = root / "research/track_a/notebooks/16_track_a_review.ipynb"
    nbformat.validate(notebook)
    nbformat.write(notebook, output)
    print(f"Validated {'executed ' if args.execute else ''}notebook: {output}")


if __name__ == "__main__":
    main()
