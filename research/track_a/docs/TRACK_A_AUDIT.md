# Đối chiếu Track A với GitHub — 2026-10-18

Đối chiếu theo brief “Customer Segmentation: RFM, CLV, Affinity, Persona (Track A)” do chủ repo cung cấp.

## Trước lần bổ sung này

Main có pipeline recommendation ở root, v2 event pipeline, sample/full Vertex benchmark và MLflow.
Tuy nhiên **bộ nghiên cứu Track A có trên máy chưa nằm trong repo này**. Vì vậy code CLV 1m/Poisson,
persona theo rule và smoothed affinity của v2 không tự chứng minh đã đáp ứng toàn bộ track.
README root còn mô tả full/MLflow như việc chưa làm và dùng từ “giao dịch”; các chỗ gây nhầm đó đã được sửa/phân biệt phạm vi.

## Checkpoint 1 — Ingest, EDA, event, RFM, lifecycle

| Yêu cầu | Trạng thái và bằng chứng |
|---|---|
| Môi trường/Git/Python, tái chạy | requirements-track-a.txt, requirements-demo.txt; [REPRODUCE.md](REPRODUCE.md), 3 workflow độc lập cho root/v2/Track A |
| Ingest/clean file lớn, chunk/Parquet | pipeline v2 ingest có chunk, typed fields, cache manifest, monthly partitions; full 13.647.309 snapshot đã chạy Vertex theo CLOUD_RUNS.md. Bước tổng hợp mỗi tháng vẫn dùng RAM, không tự nhận hoàn toàn out-of-core |
| Raw missing/cardinality/product distribution | [raw_column_audit.csv](../reports/sample_10k/raw_column_audit.csv) có renta/age/cod_prov/indrel_1mes và categorical; portfolio_distribution.csv, monthly_snapshots.csv |
| EDA sâu theo thời gian/segment/channel/tenure | [segment_product_trend.csv](../reports/sample_10k/segment_product_trend.csv), panel_presence.csv và panel_presence_by_segment.csv; không gọi absence là churn ngân hàng đã xác nhận |
| Notebook EDA ≥5–7 finding | [report với 8 finding đo lại](../reports/sample_10k/TRACK_A_REPORT.md) và [notebook demo đã execute](../notebooks/16_track_a_review.ipynb); notebook 00 gốc chỉ là research lịch sử có limitations |
| Product acquisition event | v2 pair guard + Track A export 16 partitions, **6.062 product-level events** trên sample; 0→1, consecutive complete snapshots, first-seen/gap return không tự tạo event |
| RFM quantile/KMeans/rule và stability | Notebook 01/03 gốc và [benchmark evidence](02_benchmarks.md); bổ sung [rfm_tiering_spec.json](../reports/sample_10k/rfm_tiering_spec.json), geometry và **membership** ARI/stay rate fit-fixed trên sample |
| Lifecycle dùng activity/disappearance/death | Giữ presence_lifecycle v2; export thêm activity/death-aware lifecycle và cross_sell_eligible; định nghĩa/precedence trong [feature spec](FEATURE_STORE_SPEC.md). Missing status không bị giả thành active/eligible |
| Processed dataset + dictionary | Đã materialize private `processed/customer_features_latest.parquet`, `lifecycle_latest.parquet`, acquisition events, schema/spec/manifest. Schema public: [feature_store_spec.json](../reports/sample_10k/feature_store_spec.json); định nghĩa gốc: [data_dictionary.md](data_dictionary.md) |
| Processed dataset trên **AWS S3** | **Đổi sang GCS theo lựa chọn chủ repo**, khác yêu cầu AWS S3 của brief. Processed sample đã upload, tải lại kiểm size/SHA256; [quyết định + vị trí](GCS_STORAGE.md), [receipt 20 object](../reports/sample_10k/gcs_storage_receipt.json). Không triển khai AWS S3 |

## Checkpoint 2 — CLV, affinity, MLflow

| Yêu cầu | Trạng thái và bằng chứng |
|---|---|
| BG/NBD và Gamma-Gamma | Notebook 07 gốc được đưa vào repo; chạy mới sample với [fit status](../reports/sample_10k/clv_probabilistic_fit_status.csv), cả hai fit thành công. BG/NBD frequency = repeat event-months; GG value = acquisition count/event-month proxy, không phải money |
| Gradient boosting horizon 6–12m | **6m đã chạy**, train origins 03–05/2015, cutoff 11/2015 → label end 05/2016. [Audit](../reports/sample_10k/clv_6m_audit.json). 12m chưa đủ calendar history để supervised train/validation/test hợp lệ, không bịa benchmark |
| Validation benchmark xác suất vs ML | Nghiên cứu gốc notebook 07 có validation chọn model 1m/3m và rolling test; các bảng evidence có nguồn. Benchmark 6m bổ sung là **fixed-config development backtest**, không mượn validation 1m làm 6m hoặc tự gọi independent holdout |
| So sánh khách mới/ít history, sai số theo RFM | [clv_6m_segment_errors.csv](../reports/sample_10k/clv_6m_segment_errors.csv): event history, history_short và RFM buckets. future incomplete = censored, không gán 0 |
| SHAP/giải thích CLV | [clv_6m_shap_importance.csv](../reports/sample_10k/clv_6m_shap_importance.csv), 200 sample, link `log_expected_acquisitions`; kiểm tra additive reconstruction bằng dự báo thực tế |
| Affinity 24×24, support/confidence/lift | [counts](../reports/sample_10k/affinity_counts_24x24.csv), support/confidence/lift và affinity_pair_rules.csv; next-month benchmark giữ ownership mask |
| Apriori/FPGrowth vs embedding | Notebook 06 gốc có **Apriori tối đa 3 và item2vec SGNS NumPy**, source cùng aggregate benchmark/provenance được giữ; không tuyên bố dùng mlxtend/FPGrowth hoặc gán SVD thành item2vec |
| Đo chất lượng đề xuất | [benchmark gốc](02_benchmarks.md) giữ MAP@7_all/recall7_acquirers cho Apriori, item2vec, popularity, temporal…; [benchmark sample mới](../reports/sample_10k/affinity_next_month_benchmark.csv) tách riêng cohort/phương pháp |
| MLflow comparison/log | Experiment **santander-track-a**, parent run `0ea405f68cda46588971b40dc2a6a63f`, bốn child CLV; aggregate artifacts và fit status. recommendation vẫn ở experiment santander-event-v2. Không upload customer rows vào tracking |

### Kết quả CLV 6m mới — cùng 9.417 khách có nhãn

| Phương pháp | RMSE | Capture10 |
|---|---:|---:|
| Historical mean | 0.767239 | 0.100032 |
| BG/NBD + fallback | 0.687539 | 0.532241 |
| BG/NBD + Gamma-Gamma + fallback | 0.691939 | 0.508740 |
| Gradient boosting, config cố định | 0.656428 | 0.562976 |

BG/NBD/GG có **84,07% fallback** ở current cohort; không gọi toàn bộ điểm là probabilistic thuần.
Coverage nhãn 6m **99,05%** của 9.507 current complete khách. Baseline constant được chia công bằng ở tie boundary.
Không chọn lại model hoặc quảng cáo uplift có ý nghĩa thống kê từ một cửa sổ này.

## Checkpoint 3 — Persona và tổng kết

| Yêu cầu | Trạng thái và bằng chứng |
|---|---|
| Persona từ RFM + CLV + portfolio/affinity + demographics | Thêm multiblock KMeans ở track_a/segmentation.py; fit 11/2015, log1p/scale, one-hot canal/segmento, fixed block weights; input columns được ghi trong persona_cluster_spec.json |
| Chọn số cụm/phương pháp | k=5…8, fit-only silhouette, min fit share ≥1%. Kết quả chọn **k=5**, silhouette 0.270085; KMeans/cây/rule alternatives gốc vẫn ở notebook 09/10 |
| 5–8 persona cards định lượng | [6 P1–P6 cards gốc](04_persona_cards.md) cùng individual docs/personas; **[5 C1–C5 cards mới](../reports/sample_10k/persona_cluster_cards.md)** với quy mô, median age/renta/tenure/F/portfolio, mean CLV, top channel/product |
| Stability + interpretability | Bootstrap ARI 0.733–0.993; temporal ARI 0.920–0.952, cùng common-customer coverage/stay rate. Không đồng nhất profile stability với membership, không claim clusters là chân lý hay uplift |
| Tích hợp end-to-end | CLI track_a.run nhận completed v2 run/cache, xác minh source/temporal audit, chạy EDA → event/lifecycle → RFM → CLV → affinity/persona → processed/spec/MLflow. Có source hashes và artifact riêng |
| Feature Store spec: schema/naming/versioning/TTL | [FEATURE_STORE_SPEC.md](FEATURE_STORE_SPEC.md) + generated machine schema; view version, source versions, availability/publication caveat, monthly refresh, TTL/invalidation, offline-only labels |
| Báo cáo tổng kết + benchmark/hạn chế | [TRACK_A_REPORT.md](../reports/sample_10k/TRACK_A_REPORT.md), [benchmark nghiên cứu](02_benchmarks.md), [limitations](limitations.md), [reproduce](REPRODUCE.md) |
| Demo notebook hoặc slide 15–20 phút | [16_track_a_review.ipynb](../notebooks/16_track_a_review.ipynb) có agenda **18 phút**, bảng/plot aggregate, đã execute toàn bộ cell; không cần raw/credential khi mở lại |
| Độc lập MLE GeoLife, không dùng real customer data | Không nối sang GeoLife; dữ liệu nghiên cứu Kaggle, không claim đã kiểm chứng trên dữ liệu khách production. Raw/processed/model pickle không commit |

## Kiểm chứng và provenance

- **24 test** của v2/extensions pass local; **8 test** package research wrap pass. Bao gồm kiểm tra leakage/future invariance, long-horizon censoring, đúng cutoff, BG/NBD/SHAP integration, fair ties, lifecycle unknown/death và S3 manifest validation trước network write.
- Notebook demo được thực thi bằng nbclient, không còn cell error; requirements-demo.txt tách dependencies trình bày.
- Source research import giữ SHA256 trong reports/import_manifest.json; evidence từ notebook gốc có evidence_manifest.json/source_manifest.json. Notebook gốc không chứa customer-level output.
- Sample mới giữ hash code/raw/config/source audit trong [run_provenance.json](../reports/sample_10k/run_provenance.json); [environment.json](../reports/sample_10k/environment.json) ghi versions.
- Raw/processed Parquet, pickle model và config local nằm ngoài Git. Bản local giữ fitted RFM/persona transform+model để tái sử dụng; chỉ load pickle tin cậy.

## Sai khác storage đã được chủ repo chấp nhận

Chủ repo đã xác nhận **giữ GCS thay AWS S3** và phê duyệt payload/prefix. Đã publish 19 processed data/spec files và manifest cuối vào bucket GCS hiện có, tải lại đối chiếu size/SHA256. Xem [GCS_STORAGE.md](GCS_STORAGE.md). Đây là thay thế nền tảng, không đánh dấu yêu cầu AWS S3 là đã triển khai.

Bổ sung **3 test GCS publisher** pass: dry-run không network, chặn file/path không hợp lệ trước upload, đọc đúng metadata nested/flat của gcloud. Tổng test local: 24 v2 + 8 wrap gốc + 3 GCS = **35**; notebook demo được execute lại sau cập nhật storage.
Các việc production như serving, campaign A/B, Model Registry hay triển khai Feature Store không phải deliverable của track này và không được tự gán là đã làm.
