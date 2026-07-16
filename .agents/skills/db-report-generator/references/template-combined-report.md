# BÁO CÁO TỔNG HỢP: {{ProjectName}}
## Ngày: {{report_date}}
## Database: {{CatalogName}} @ {{ServerName}}
## Code: {{CodePath}}

---

## BẢNG ĐIỀU KHIỂN TỔNG QUAN

| Hạng Mục | Điểm | Trạng Thái |
|----------|------|------------|
| **Sức Khỏe Database** | {{db_score}}/100 | {{db_status_icon}} |
| **Chất Lượng Code (Lớp DB)** | {{code_score}}/100 | {{code_status_icon}} |
| **Bảo Mật** | {{security_score}}/100 | {{security_status_icon}} |
| **Hiệu Suất** | {{perf_score}}/100 | {{perf_status_icon}} |
| **TỔNG** | **{{total_score}}/100** | **{{total_status_icon}}** |

### Quy Ước Điểm
- 🟢 90-100: Xuất sắc
- 🟡 70-89: Tốt, có điểm cần cải thiện
- 🟠 50-69: Cần chú ý
- 🔴 0-49: Nghiêm trọng, cần xử lý ngay

---

## VẤN ĐỀ HÀNG ĐẦU (Ưu Tiên Xử Lý)

| # | Loại | Mức Độ | Mô Tả | File/Bảng | Khuyến Nghị |
|---|------|--------|--------|-----------|-------------|
{{#each top_issues}}
| {{@index}} | {{type}} | {{severity_icon}} | {{description}} | {{location}} | {{recommendation}} |
{{/each}}

---

## THAM CHIẾU CHÉO: DB ↔ CODE

### Bảng Có Vấn Đề Cả DB Lẫn Code

| Bảng | Vấn Đề DB | Vấn Đề Code | Tác Động |
|------|-----------|-------------|----------|
{{#each cross_issues}}
| {{table}} | {{db_issue}} | {{code_issue}} | {{impact}} |
{{/each}}

---

## TÓM TẮT GIẢI PHÁP HIỆU SUẤT

Xem chi tiết: [PERFORMANCE_SOLUTIONS.md](./PERFORMANCE_SOLUTIONS.md)

| Độ Ưu Tiên | Số Lượng | Vấn Đề Hàng Đầu |
|------------|----------|-----------------|
| **P0 Nghiêm trọng** | {{p0_count}} | {{p0_top_issue}} |
| **P1 Ưu tiên cao** | {{p1_count}} | {{p1_top_issue}} |
| **P2 Trung bình** | {{p2_count}} | {{p2_top_issue}} |
| **P3 Thấp** | {{p3_count}} | {{p3_top_issue}} |
| **TỔNG** | **{{total_solutions}}** | **{{total_scripts}} script sẵn sàng chạy** |

### Top 5 Giải Pháp (Ưu Tiên Cao Nhất)

| # | Độ Ưu Tiên | Giải Pháp | Tác Động Dự Kiến | Danh Mục |
|---|-----------|-----------|-----------------|----------|
{{#each top_5_solutions}}
| {{@index}} | **{{priority}}** | {{title}} | {{impact}} | {{category}} |
{{/each}}

---

## CHI TIẾT

- 📊 [Báo cáo Database đầy đủ](./DB_STATUS_REPORT.md)
- 💻 [Báo cáo Code đầy đủ](./CODE_ANALYSIS_REPORT.md)
- ⭐ [Giải pháp Hiệu suất](./PERFORMANCE_SOLUTIONS.md)

---

*Báo cáo được tạo tự động bởi db-report-generator v3.0.0 kết hợp supabase-postgres-best-practices*
*Thời gian tạo: {{generated_at}}*
