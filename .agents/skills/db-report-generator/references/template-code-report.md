# BÁO CÁO PHÂN TÍCH CODE - {{ProjectName}}
## Ngày kiểm tra: {{report_date}}
## Database liên quan: {{CatalogName}} @ {{ServerName}}
## Thư mục code: {{CodePath}}

---

## 1. TỔNG QUAN DỰ ÁN

| Chỉ Số | Giá Trị |
|--------|---------|
| **Tổng số files** | {{total_files}} |
| **Tổng số dòng code** | {{total_lines}} |
| **Ngôn ngữ chính** | {{primary_language}} |
| **Framework** | {{framework}} |
| **Số Models/Entities** | {{total_models}} |
| **Số API Endpoints** | {{total_endpoints}} |
| **Số truy vấn SQL thô** | {{total_raw_queries}} |

---

## 2. CẤU TRÚC DỰ ÁN

```
{{project_tree}}
```

---

## 3. PHÂN TÍCH TRUY CẬP DATABASE

### 3.1 ORM / Lớp Truy Cập Dữ Liệu

| Loại | Số Lượng | Chi Tiết |
|------|----------|----------|
| Lớp Entity/Model | {{model_count}} | {{model_list}} |
| Lớp Repository/DAO | {{repo_count}} | {{repo_list}} |
| File migration | {{migration_count}} | - |
| Truy vấn SQL thô | {{raw_sql_count}} | Xem chi tiết bên dưới |

### 3.2 Truy Vấn SQL Thô Tìm Được

{{#each raw_queries}}
**File:** `{{file_path}}:{{line_number}}`
```sql
{{query_text}}
```
**Đánh giá:** {{assessment}}

---
{{/each}}

### 3.3 Mẫu N+1 Query (Tiềm Ẩn)

{{#each n_plus_one_patterns}}
| File | Dòng | Mẫu | Mô Tả |
|------|------|-----|--------|
| `{{file_path}}` | {{line}} | {{pattern_type}} | {{description}} |
{{/each}}

---

## 4. PHÂN TÍCH BẢO MẬT (SQL Injection)

### 4.1 Nối Chuỗi Trong Truy Vấn

{{#if has_sql_injection_risk}}
⚠️ **Phát hiện rủi ro SQL Injection:**

| # | File | Dòng | Đoạn Code | Mức Độ |
|---|------|------|-----------|--------|
{{#each sql_injection_risks}}
| {{@index}} | `{{file_path}}` | {{line}} | `{{snippet}}` | {{severity}} |
{{/each}}

**Khuyến nghị:** Sử dụng parameterized queries thay vì nối chuỗi.
{{else}}
✅ Không phát hiện rủi ro SQL Injection rõ ràng.
{{/if}}

### 4.2 Thông Tin Xác Thực Cứng Trong Code

{{#if has_hardcoded_creds}}
🔴 **Phát hiện credentials hardcoded:**

| # | File | Dòng | Loại |
|---|------|------|------|
{{#each hardcoded_creds}}
| {{@index}} | `{{file_path}}` | {{line}} | {{type}} |
{{/each}}
{{else}}
✅ Không phát hiện thông tin xác thực cứng trong code.
{{/if}}

---

## 5. ÁNH XẠ: CODE ↔ DATABASE

### 5.1 Bảng Được Sử Dụng Trong Code

| # | Tên Bảng | Entity/Model | Repository | Số Truy Vấn | Files Liên Quan |
|---|----------|-------------|------------|-------------|----------------|
{{#each table_mappings}}
| {{@index}} | {{table_name}} | {{entity_name}} | {{repo_name}} | {{query_count}} | {{related_files}} |
{{/each}}

### 5.2 Bảng Có Trong DB Nhưng KHÔNG Có Trong Code

{{#each orphan_tables}}
- `{{this}}` - Có thể là bảng legacy hoặc dùng bởi service khác
{{/each}}

### 5.3 Bảng Có Trong Code Nhưng KHÔNG Có Trong DB

{{#each missing_tables}}
- `{{this}}` - Có thể chưa migration hoặc sai tên
{{/each}}

---

## 6. PHÂN TÍCH HIỆU SUẤT CODE

### 6.1 Truy Vấn Không Có Phân Trang

{{#each no_pagination_queries}}
| File | Dòng | Truy Vấn/Phương Thức | Bảng | Số Dòng Trong DB |
|------|------|---------------------|------|-----------------|
| `{{file_path}}` | {{line}} | `{{method}}` | {{table}} | {{row_count}} |
{{/each}}

### 6.2 Mẫu SELECT *

{{#each select_star_patterns}}
| File | Dòng | Bảng | Số Cột |
|------|------|------|--------|
| `{{file_path}}` | {{line}} | {{table}} | {{column_count}} |
{{/each}}

### 6.3 Index Còn Thiếu Cho Truy Vấn Trong Code

| # | Mẫu Truy Vấn (WHERE/JOIN) | Bảng | Cột | Có Index? | File |
|---|---------------------------|------|-----|-----------|------|
{{#each query_index_analysis}}
| {{@index}} | {{query_pattern}} | {{table}} | {{columns}} | {{has_index}} | `{{file_path}}` |
{{/each}}

---

## 7. QUẢN LÝ KẾT NỐI

### 7.1 Cấu Hình Connection Pool

| Tham Số | Giá Trị | Khuyến Nghị |
|---------|---------|-------------|
| Kích thước Pool | {{pool_size}} | {{pool_recommendation}} |
| Timeout | {{conn_timeout}} | {{timeout_recommendation}} |
| Idle Timeout | {{idle_timeout}} | {{idle_recommendation}} |

### 7.2 Rò Rỉ Kết Nối (Tiềm Ẩn)

{{#each connection_leak_risks}}
| File | Dòng | Mẫu | Mô Tả |
|------|------|-----|--------|
| `{{file_path}}` | {{line}} | {{pattern}} | {{description}} |
{{/each}}

---

## 8. TỔNG KẾT & KHUYẾN NGHỊ

### 🔴 Vấn Đề Nghiêm Trọng
{{#each critical_code_issues}}
- [ ] {{this}}
{{/each}}

### 🟡 Cần Cải Thiện
{{#each code_warnings}}
- [ ] {{this}}
{{/each}}

### ✅ Tình Trạng Tốt
{{#each code_good_status}}
- [x] {{this}}
{{/each}}

### 📋 Hạng Mục Cần Xử Lý
{{#each action_items}}
- [ ] **[{{priority}}]** {{description}} - File: `{{file_path}}`
{{/each}}

---

*Báo cáo được tạo tự động bởi db-report-generator v3.0.0*
*Thời gian tạo: {{generated_at}}*
