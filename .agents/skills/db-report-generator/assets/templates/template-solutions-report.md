# GIẢI PHÁP HIỆU SUẤT - {{ProjectName}}
## Ngày: {{report_date}}
## Database: {{CatalogName}} @ {{ServerName}}:{{Port}}
## Nguồn: DB_STATUS_REPORT.md + CODE_ANALYSIS_REPORT.md + supabase-postgres-best-practices

---

## TÓM TẮT TỔNG QUAN

| Chỉ Số | Giá Trị |
|--------|---------|
| **Tổng vấn đề phát hiện** | {{total_problems}} |
| **P0 Nghiêm trọng** | {{p0_count}} |
| **P1 Ưu tiên cao** | {{p1_count}} |
| **P2 Trung bình** | {{p2_count}} |
| **P3 Thấp** | {{p3_count}} |
| **Script sẵn sàng chạy** | {{script_count}} |
| **Cải thiện hiệu suất dự kiến** | {{impact_summary}} |

---

## QUY ƯỚC ĐỘ ƯU TIÊN

| Độ Ưu Tiên | Nhãn | Thời Hạn Xử Lý | Ví Dụ |
|-------------|------|-----------------|-------|
| **P0** | NGHIÊM TRỌNG | Xử lý trong 24h | SQL injection, cache <50%, blocking, kết nối >90% |
| **P1** | ƯU TIÊN CAO | Xử lý trong 1 tuần | Truy vấn chậm >1s, mẫu N+1, thiếu index FK |
| **P2** | TRUNG BÌNH | Xử lý trong 1 tháng | Index không dùng, tinh chỉnh cấu hình, SELECT * |
| **P3** | THẤP | Sprint sau | Index phình, index trùng lặp, covering index |

---

## P0 - GIẢI PHÁP NGHIÊM TRỌNG

{{#each p0_solutions}}
### P0-{{@index}}. {{title}}

| Thuộc Tính | Chi Tiết |
|------------|----------|
| **Vấn đề** | {{problem_description}} |
| **Giá trị phát hiện** | {{detected_value}} |
| **Ngưỡng cho phép** | {{threshold}} |
| **Phạm vi ảnh hưởng** | {{affected_area}} |
| **Danh mục** | {{category}} |
| **Tác động dự kiến** | {{expected_impact}} |
| **Mức rủi ro** | {{risk_level}} |
| **Tham chiếu best practice** | {{best_practice_ref}} |

**Nguyên nhân gốc:**
{{root_cause}}

**Cách sửa:**
```sql
{{fix_sql}}
```

**Xác minh (chạy sau khi sửa):**
```sql
{{verify_sql}}
```

**recovery_or_rollback (nếu cần revert):**
```sql
{{recovery_or_rollback_sql}}
```

---
{{/each}}

{{#if no_p0}}
> ✅ Không có vấn đề P0 Nghiêm trọng. Database đang ở trạng thái ổn định.
{{/if}}

---

## P1 - GIẢI PHÁP ƯU TIÊN CAO

{{#each p1_solutions}}
### P1-{{@index}}. {{title}}

| Thuộc Tính | Chi Tiết |
|------------|----------|
| **Vấn đề** | {{problem_description}} |
| **Giá trị phát hiện** | {{detected_value}} |
| **Phạm vi ảnh hưởng** | {{affected_area}} |
| **Danh mục** | {{category}} |
| **Tác động dự kiến** | {{expected_impact}} |
| **Tham chiếu best practice** | {{best_practice_ref}} |

**Nguyên nhân gốc:**
{{root_cause}}

**Cách sửa:**
```sql
{{fix_sql}}
```

**Xác minh:**
```sql
{{verify_sql}}
```

---
{{/each}}

---

## P2 - GIẢI PHÁP TRUNG BÌNH

{{#each p2_solutions}}
### P2-{{@index}}. {{title}}

| Thuộc Tính | Chi Tiết |
|------------|----------|
| **Vấn đề** | {{problem_description}} |
| **Phạm vi ảnh hưởng** | {{affected_area}} |
| **Danh mục** | {{category}} |
| **Tác động dự kiến** | {{expected_impact}} |

**Cách sửa:**
```sql
{{fix_sql}}
```

---
{{/each}}

---

## P3 - GIẢI PHÁP ĐỘ ƯU TIÊN THẤP

{{#each p3_solutions}}
### P3-{{@index}}. {{title}}

| Vấn Đề | Cách Sửa | Tác Động |
|---------|----------|----------|
| {{problem_description}} | `{{fix_short}}` | {{expected_impact}} |

{{/each}}

---

## SCRIPT SQL SẴN SÀNG CHẠY

> **CẢNH BÁO**: Review kỹ trước khi chạy. Luôn test trên staging trước.
> Scripts sắp xếp theo độ ưu tiên. Chạy P0 trước.
> Các fix có `remediation_class: dangerous` KHÔNG BAO GIỜ xuất hiện trong các script dưới đây — xem mục "GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)" bên dưới.

### Script 1: Sửa Lỗi P0 Nghiêm Trọng
```sql
-- ================================================
-- SỬA LỖI P0 NGHIÊM TRỌNG - {{report_date}}
-- Database: {{CatalogName}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p0_scripts}}
-- [P0-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 2: Sửa Lỗi P1 Ưu Tiên Cao
```sql
-- ================================================
-- SỬA LỖI P1 ƯU TIÊN CAO - {{report_date}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p1_scripts}}
-- [P1-{{@index}}] {{description}}
-- Dự kiến: {{impact}}
{{sql}}

{{/each}}
```

### Script 3: Sửa Lỗi P2 Trung Bình
```sql
-- ================================================
-- SỬA LỖI P2 TRUNG BÌNH - {{report_date}}
-- (Đã loại trừ mọi fix remediation_class=dangerous)
-- ================================================

{{#each p2_scripts}}
-- [P2-{{@index}}] {{description}}
{{sql}}

{{/each}}
```

### GIẢI PHÁP CẦN REVIEW THỦ CÔNG (DANGEROUS)

> Các fix dưới đây thuộc tier `dangerous` (DROP INDEX, pg_terminate_backend, partition migration, ALTER SYSTEM, ...). KHÔNG được đưa vào script chạy-liền ở trên — mỗi fix cần được đọc, hiểu rủi ro, và chạy thủ công từng câu lệnh một sau khi review.

{{#each dangerous_solutions}}
#### {{description}}

**Lý do dangerous**: {{danger_reason}}

```sql
{{fix_sql}}
```

**recovery_or_rollback:**
```sql
{{recovery_or_rollback_sql}}
```

{{/each}}
{{#if no_dangerous}}
_Không có phát hiện nào thuộc tier `dangerous` trong lần phân tích này._
{{/if}}

---

## GIẢI PHÁP PHÍA CODE

{{#each code_solutions}}
### {{priority}}-C{{@index}}. {{title}}

**Vấn đề:** {{problem_description}}
**File:** `{{file_path}}:{{line_number}}`
**Danh mục:** {{category}}

**Code hiện tại (có vấn đề):**
```{{language}}
{{current_code}}
```

**Code khuyến nghị:**
```{{language}}
{{fixed_code}}
```

**Giải thích:**
{{explanation}}

**Tác động dự kiến:** {{impact}}

---
{{/each}}

{{#if no_code_solutions}}
> ℹ️ Không có CodePath được cấu hình, hoặc không phát hiện vấn đề code.
{{/if}}

---

## KHUYẾN NGHỊ KIẾN TRÚC

{{#each arch_recommendations}}
### ARCH-{{@index}}. {{title}} ({{priority}})

| Thuộc Tính | Chi Tiết |
|------------|----------|
| **Trạng thái hiện tại** | {{current_state}} |
| **Khuyến nghị** | {{recommendation}} |
| **Mức độ nỗ lực** | {{effort}} |
| **Tác động dự kiến** | {{impact}} |

{{#if has_implementation}}
**Triển khai:**
```sql
{{implementation_sql}}
```
{{/if}}

{{#if has_code}}
**Thay đổi code:**
```{{language}}
{{implementation_code}}
```
{{/if}}

---
{{/each}}

---

## CHECKLIST THEO DÕI GIẢI PHÁP

Sử dụng checklist này để theo dõi tiến trình triển khai:

| # | Độ Ưu Tiên | Giải Pháp | Trạng Thái | Đã Áp Dụng | Đã Xác Minh |
|---|-----------|-----------|------------|------------|-------------|
{{#each all_solutions}}
| {{@index}} | **{{priority}}** | {{title}} | [ ] Chờ xử lý | - | - |
{{/each}}

### Hướng Dẫn Sử Dụng Checklist
1. Copy checklist vào issue tracker (Jira, GitHub Issues, v.v.)
2. Áp dụng các bản sửa theo thứ tự ưu tiên (P0 → P1 → P2 → P3)
3. Sau mỗi bản sửa, chạy câu lệnh Xác minh để kiểm tra
4. Chạy lại db-report-generator ngày hôm sau để so sánh chỉ số

---

{{#if has_previous_report}}
## SO SÁNH VỚI LẦN TRƯỚC ({{previous_date}})

| Chỉ Số | Lần Trước | Lần Này | Xu Hướng |
|--------|-----------|---------|----------|
| Tổng vấn đề | {{prev_total}} | {{total_problems}} | {{total_trend}} |
| P0 Nghiêm trọng | {{prev_p0}} | {{p0_count}} | {{p0_trend}} |
| P1 Ưu tiên cao | {{prev_p1}} | {{p1_count}} | {{p1_trend}} |
| Giải pháp đã áp dụng | {{prev_applied}} | - | - |

{{/if}}

---

*Báo cáo được tạo tự động bởi db-report-generator v4.0.0 kết hợp supabase-postgres-best-practices*
*Thời gian tạo: {{generated_at}}*
