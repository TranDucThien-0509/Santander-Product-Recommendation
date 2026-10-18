# Giới hạn và phạm vi bằng chứng

1. Chỉ có snapshot sở hữu, không có giao dịch, phí, dư nợ hay lợi nhuận thực. M và CLV ở đây là acquisition proxy.
2. Left truncation: F=0 không có nghĩa chưa bao giờ mở sản phẩm. Reopen được tính acquisition.
3. Presence trong dataset không đồng nghĩa sử dụng thực; disappearance không chứng minh đóng tài khoản.
4. Target acquisition t+1 chỉ được đo trên cặp đầy đủ, tạo selection bias; không điền khách vắng thành negative.
5. Đã khảo sát nhiều cấu hình trên Dec2015–Apr2016. Các kết quả này là development/backtest; không có holdout mới để đưa ra claim mới.
6. CLV fit lại ở mỗi origin với nhãn hoàn tất, selection method giữ từ validation. Các tháng dài horizon có overlap, không độc lập.
7. BG/NBD score toàn cohort gồm baseline fallback cho ~80–84% khách ở các tháng test; không gọi là BG/NBD thuần cho mọi khách.
8. Gamma-Gamma là thử nghiệm proxy; points=acquisitions khi mọi product weight=1, không phải hai target độc lập.
9. Income missing theo persona/địa lý; median chỉ phản ánh phần có dữ liệu. Correlation thấp không chứng minh biến vô dụng.
10. Persona card chỉ mô tả; không có causal uplift hoặc measured marketing profit. Đặc điểm ổn định không chứng minh membership ổn định.
11. Input 06/07 có thể dùng tag F3; output13/audit persona F4. Wrap giữ nguồn riêng, không tuyên bố model đã train lại.
12. Source notebook 00 là nghiên cứu lịch sử chưa sửa các vấn đề đã audit: tuổi <=18 bị gộp, Added chưa kiểm tra gap, cohort June/July dùng cả hai tháng và một số diễn giải churn/seasonality quá mạnh. Không dùng các kết luận đó làm bằng chứng cuối. Wrap/14 đọc lại raw riêng.
13. Một số Markdown nguồn còn ghi 'chưa chạy' hoặc câu hỏi sau Run All dù có output. Evidence docs lấy từ output đã lưu, không coi lời dẫn cũ là kết quả.
14. Pipeline mới không tải dữ liệu Kaggle, không deploy, không tạo campaign và không đẩy GitHub tự động.
