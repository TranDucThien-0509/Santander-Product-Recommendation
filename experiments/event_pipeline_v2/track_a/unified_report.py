"""Render aggregate benchmark evidence without publishing customer-level rows."""
import base64
import html
import json

import numpy as np
import pandas as pd


def render_report(out, tables, manifest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = manifest["methods"]
    latest = manifest["origins"][-1]
    customer = tables["customer_metrics_by_month"]
    selected = customer.loc[customer.origin.eq(latest)].copy()
    selected["Phương pháp"] = selected.method.map(names)
    display = selected[["Phương pháp","AP","AUC","lift10_buyers","capture10_products","Brier"]].rename(columns={
        "lift10_buyers":"Lift10 khách","capture10_products":"Capture10 sản phẩm"})
    mean = tables["customer_metrics_monthly_mean"].copy()
    mean["Phương pháp"] = mean.method.map(names)
    mean = mean[["Phương pháp","AP","AUC","lift10_buyers","capture10_products"]].rename(columns={
        "lift10_buyers":"Lift10 khách","capture10_products":"Capture10 sản phẩm"})
    product = tables["product_metrics_by_month"]
    product = product.loc[product.origin.eq(latest),["method","n_all","n_buyers","map_at_7_all","map_at_7_buyers","recall_at_7_buyers","evaluation_mode"]].copy()
    cohorts = tables["cohort_audit"][["origin","target_month","n_all","n_buyers","product_acquisitions","pair_coverage"]]
    stability = tables["group_stability_by_month"]
    stability_display = stability.groupby("method",sort=False)[["same_label_rate","membership_ARI","rate_rank_spearman"]].mean().reset_index() if not stability.empty else stability

    selected = selected.sort_values("lift10_buyers")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11})
    fig, ax = plt.subplots(figsize=(11,6),layout="constrained")
    ax.barh(selected.method.map(names),selected.lift10_buyers,color="#1565C0")
    ax.axvline(1,color="#7086A0",linestyle="--",linewidth=1)
    ax.set(xlabel="Lift@10% khách có mở thêm",title=f"Cùng cohort test {latest}: ưu tiên khách hàng")
    for i,value in enumerate(selected.lift10_buyers):
        ax.text(value+.04,i,f"{value:.2f}",va="center",fontsize=10)
    ax.set_xlim(0,max(1,float(selected.lift10_buyers.max()))*1.15)
    ax.spines[["right","top"]].set_visible(False)
    fig.savefig(out/"test_customer_lift.png",dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11,5),layout="constrained")
    for method in ["rfm_portfolio_propensity","rfm_kmeans_6","lifecycle_presence","lifecycle_activity","clv_poisson_1m","affinity_max"]:
        part = customer.loc[customer.method.eq(method)].sort_values("origin")
        ax.plot(part.origin,part.lift10_buyers,marker="o",label=names[method])
    ax.axhline(1,color="#7086A0",linestyle="--",linewidth=1)
    ax.set(xlabel="Tháng chấm điểm (nhãn ở tháng kế tiếp)",ylabel="Lift@10% khách có mở thêm",title="Khả năng ưu tiên khách qua các tháng")
    ax.legend(fontsize=9,loc="upper left",bbox_to_anchor=(1.01,1))
    ax.spines[["right","top"]].set_visible(False)
    fig.savefig(out/"customer_lift_by_month.png",dpi=150)
    plt.close(fig)

    def markdown(frame):
        # Avoid an extra tabulate dependency in the CLI environment.
        def format_value(value):
            if pd.isna(value):
                return "—"
            if isinstance(value,(float,np.floating)):
                return f"{value:.6f}"
            return str(value).replace("|","/")
        return "\n".join(["| "+" | ".join(map(str,frame.columns))+" |",
            "|"+"---|"*len(frame.columns),*["| "+" | ".join(map(format_value,row))+" |" for row in frame.itertuples(index=False,name=None)]])

    caveats = [
        "Đây là rolling development backtest trên cùng nguồn v2; các tháng đã được dùng trong nghiên cứu trước. Không gọi là holdout chưa từng xem.",
        "Mọi phương pháp dùng đúng cùng cặp snapshot liên tiếp đầy đủ tại mỗi tháng. Không lọc riêng người mua, khách có lịch sử dài hoặc trạng thái active cho từng phương pháp.",
        "Mục tiêu chung là có mở thêm ít nhất một sản phẩm ở tháng kế tiếp. Capture sản phẩm và RMSE dùng mục tiêu đếm số sản phẩm mở thêm, được ghi thành cột riêng.",
        "Top 10% dùng trọng số phân số cho toàn bộ nhóm đồng điểm ở ngưỡng chọn. Không phá hòa theo ID. Baseline điểm bằng nhau luôn có lift 1.",
        "RFM group, lifecycle và persona được chuyển thành điểm bằng tỷ lệ mở thêm trong các cặp lịch sử đã hoàn tất, làm trơn với 100 cặp giả theo tỷ lệ chung. Đây là adapter đánh giá mới, không phải tái tạo các scorecard notebook gốc.",
        "K-means và ngưỡng phân vị fit một lần trên toàn cohort đầy đủ ở tháng fit, không dùng nhãn, rồi giữ nguyên. Điểm nhóm chỉ cập nhật bằng nhãn đã biết đến tháng chấm điểm.",
        "Lifecycle presence là feature catalog v2. Lifecycle activity/death là enrichment riêng của dashboard; kết quả được báo thành dòng riêng. Cohort này chỉ gồm khách đang quan sát đầy đủ, nên không kiểm định trạng thái khách vắng At-risk/Churned của presence lifecycle.",
        "CLV là baseline-numeric Poisson boosting 1 tháng đã lưu tại từng origin. Brier của CLV dùng phép đổi 1-exp(-lambda), dựa trên giả định Poisson; không tuyên bố đã hiệu chỉnh xác suất riêng.",
        "Affinity dùng đúng công thức temporal v2, window 3 tháng, prior 1000, thứ tự PRODUCTS cố định và mask sản phẩm đang sở hữu. Điểm khách hàng là affinity cao nhất trong các sản phẩm chưa sở hữu. Đây là adapter ưu tiên khách mới, không phải xác suất đã hiệu chỉnh. Brier của affinity để trống.",
        "Bảng recommendation đánh giá affinity và popularity bằng cùng nhãn 24 sản phẩm. Dòng saved_v2_evaluation_ranker nhập từ test report đã hoàn tất, kiểm tra số khách/số người mua khớp; không nói đã chạy lại dự đoán của ranker.",
        "Rate-rank Spearman đo thứ hạng tỷ lệ acquisition của nhóm có ít nhất 100 khách ở cả hai tháng; membership ARI/stay rate đo thành viên. Hai loại ổn định có ý nghĩa khác nhau.",
        "Không so các trị số lift này với lift đồng sở hữu sản phẩm 24×24 hoặc kết luận hiệu quả can thiệp marketing. Không trộn số notebook gốc vào bảng này.",
    ]
    notes = [
        "AP là average precision của nhãn có acquisition. AUC đo phân biệt người có và không có acquisition.",
        "Lift10 khách = tỷ lệ người có acquisition trong top 10% / tỷ lệ chung cùng cohort.",
        "Capture10 sản phẩm = số product acquisitions có trọng số ở top 10% / tổng acquisitions. Lift10 sản phẩm = Capture10 / 0,1.",
        "Brier càng thấp càng tốt, chỉ có khi adapter có xác suất sự kiện. MAE/RMSE/calibration count chỉ báo cho CLV trong CSV.",
        "MAP@7 all = MAP@7 buyers × tỷ lệ buyers theo đúng code hiện tại. MAP all tối đa bằng buyer prevalence; recall buyers có trần riêng nếu một khách mở quá 7 sản phẩm.",
        "Các bảng trung bình dùng trọng số bằng nhau cho từng tháng, không gọi là kết quả pooled và không gọi n_all của nhiều tháng là số khách duy nhất.",
    ]
    def section(title,frame):
        return ["\n## "+title,"",markdown(frame)]
    md = ["# Track A — Đánh giá thống nhất v2", "",
        f"Nguồn: `{manifest['source_run']}`. Phạm vi: **{manifest['scope']}**.",
        f"Tháng chấm điểm: {', '.join(manifest['origins'])}. Tháng fit RFM: {manifest['rfm_fit']['fit_month']}. Test được đánh dấu trong config nguồn: {', '.join(manifest['source_test_origins'])}."]
    md += section("1. Cùng cohort và cùng nhãn",cohorts)
    md += section("2. Ưu tiên khách hàng — tháng cuối",display)
    md += ["", "![Lift test](test_customer_lift.png)"]
    md += section("3. Trung bình đều các tháng",mean)
    md += ["", "![Lift theo tháng](customer_lift_by_month.png)"]
    md += section("4. Gợi ý sản phẩm — tháng cuối",product)
    md += section("5. Ổn định nhóm — trung bình các cặp tháng",stability_display)
    md += ["\n## Cách đọc độ đo","",*["- "+note for note in notes],"\n## Phạm vi và giới hạn","",*["- "+note for note in caveats],
        "\n## Các file chi tiết","",
        "- `customer_metrics_by_month.csv`: AP/AUC/lift/capture/Brier, lỗi count, fallback và cohort hash của từng phương pháp/tháng.",
        "- `product_metrics_by_month.csv`: MAP@7, Recall@7, mẫu số, trần lý thuyết và nguồn tính.",
        "- `group_rates_by_month.csv`: n, events, acquisition rate, KTC Wilson 95%, lift nhóm và điểm ước tính từ quá khứ.",
        "- `group_stability_by_month.csv`: rate-rank Spearman, membership ARI và stay rate.",
        "- `cohort_audit.csv`: coverage, loại trừ, số người mua, tổng acquisitions và hash tập ID (không chứa ID cá nhân).",
        "- Manifest đầy đủ và hash nguồn lưu trong output private; bản báo cáo chỉ chứa aggregate."]
    (out/"README.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    def table_html(frame):
        return frame.to_html(index=False,border=0,float_format=lambda value:f"{value:.6f}",na_rep="—",escape=True)
    def image_html(name):
        data = base64.b64encode((out/name).read_bytes()).decode()
        return f'<img src="data:image/png;base64,{data}" alt="{html.escape(name)}">'
    pieces = ["<!doctype html><html lang='vi'><meta charset='utf-8'><title>Track A — Đánh giá thống nhất v2</title>",
        "<style>body{font:16px/1.6 Arial,sans-serif;color:#123b72;background:#f3f7fc;margin:0}main{max-width:1200px;margin:35px auto;background:white;padding:40px;border-radius:18px}h1,h2{line-height:1.3}h2{margin-top:40px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #dce6f3}th{background:#edf5ff}img{width:100%;height:auto}li{margin:9px 0}.scroll{overflow:auto}</style><main>",
        "<h1>Track A — Đánh giá thống nhất v2</h1>",f"<p>Nguồn: {html.escape(manifest['source_run'])}. {html.escape(manifest['scope'])}.</p>"]
    for title,frame in [("Cohort chung",cohorts),(f"Ưu tiên khách hàng — {latest}",display),("Trung bình đều các tháng",mean),("Gợi ý sản phẩm — tháng cuối",product),("Ổn định nhóm",stability_display)]:
        pieces += [f"<h2>{html.escape(title)}</h2><div class='scroll'>",table_html(frame),"</div>"]
        if title.startswith("Ưu tiên"):
            pieces.append(image_html("test_customer_lift.png"))
        elif title.startswith("Trung bình"):
            pieces.append(image_html("customer_lift_by_month.png"))
    for title,items in [("Cách đọc độ đo",notes),("Phạm vi và giới hạn",caveats)]:
        pieces += [f"<h2>{title}</h2><ul>",*["<li>"+html.escape(item)+"</li>" for item in items],"</ul>"]
    pieces.append("</main></html>")
    (out/"report.html").write_text("\n".join(pieces),encoding="utf-8")
