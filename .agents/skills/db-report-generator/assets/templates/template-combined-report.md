# BÁO CÁO TỔNG HỢP: {{ProjectName}}
## Ngày: {{report_date}}
## Database: {{CatalogName}} @ {{ServerName}}
## Code: {{CodePath}}

---

## MA TRẬN TRỤC (AXIS MATRIX)

| Trục | Trạng thái | Độ tin cậy | Ghi chú |
|------|-----------|-----------|---------|
| DB Health | {{db_health_icon}} | {{db_health_confidence}} | {{db_health_note}} |
| Query Performance | {{query_performance_icon}} | {{query_performance_confidence}} | {{query_performance_note}} |
| Maintenance | {{maintenance_icon}} | {{maintenance_confidence}} | {{maintenance_note}} |
| Connections | {{connections_icon}} | {{connections_confidence}} | {{connections_note}} |
| Security/RLS | {{security_rls_icon}} | {{security_rls_confidence}} | {{security_rls_note}} |

**Quy Ước Ký Hiệu:**
- 🟢 green — không phát hiện vấn đề ở ngưỡng đã đo
- 🟡 yellow — cảnh báo sớm, cần theo dõi
- 🔴 red — vấn đề nghiêm trọng, cần xử lý
- ⚪ unknown — dữ liệu không đủ tin cậy để đánh giá (không được nâng cấp lên green/yellow/red — spec §0.B3)
- ➖ not_applicable — trục không áp dụng cho hệ thống này

**Độ tin cậy:** `measured` (đo trực tiếp) > `estimated` (suy ra từ mẫu) > `heuristic` (suy đoán, độ tin cậy thấp nhất — luôn đi kèm `unknown` theo §0.B3).

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
