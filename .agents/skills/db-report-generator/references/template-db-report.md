# BÁO CÁO TÌNH TRẠNG DATABASE {{CatalogName}}
## Ngày kiểm tra: {{report_date}}
## Server: {{ServerName}}:{{Port}}

---

## 1. TỔNG QUAN

| Chỉ Số | Giá Trị | Đánh Giá |
|--------|---------|----------|
| **Dung lượng DB** | {{db_size}} | {{db_size_status}} |
| **Phiên bản PostgreSQL** | {{pg_version}} | - |
| **Thời gian hoạt động** | {{uptime}} | {{uptime_status}} |
| **Kết nối đang hoạt động** | {{active_conn}} | {{active_conn_status}} |
| **Tổng kết nối** | {{total_conn}} / {{max_conn}} | {{conn_status}} |
| **Tỷ lệ Cache Hit** | {{cache_hit_ratio}}% | {{cache_status}} |

**Quy ước đánh giá Cache Hit:**
- 🟢 Tốt: > 95%
- 🟡 Cần cải thiện: 80-95%
- 🔴 Nghiêm trọng: < 80%

{{#if has_previous_report}}
### So Sánh Với Lần Trước ({{previous_date}})

| Chỉ Số | Lần trước | Lần này | Thay đổi | Xu hướng |
|--------|-----------|---------|----------|----------|
| Tỷ lệ Cache Hit | {{prev_cache_hit}}% | {{cache_hit_ratio}}% | {{cache_diff}} | {{cache_trend}} |
| Dung lượng DB | {{prev_db_size}} | {{db_size}} | {{size_diff}} | {{size_trend}} |
| Kết nối hoạt động | {{prev_active_conn}} | {{active_conn}} | {{conn_diff}} | {{conn_trend}} |
{{/if}}

---

## 2. CẤU HÌNH SERVER

| Tham Số | Giá Trị | Khuyến Nghị |
|---------|---------|-------------|
| shared_buffers | {{shared_buffers}} | 25% RAM |
| work_mem | {{work_mem}} | 50-256MB |
| maintenance_work_mem | {{maintenance_work_mem}} | 512MB-2GB |
| effective_cache_size | {{effective_cache_size}} | 75% RAM |
| max_connections | {{max_connections}} | Tùy workload |

---

## 3. TỶ LỆ CACHE HIT THEO BẢNG (Top 20)

| # | Schema | Tên Bảng | Đọc Từ Đĩa | Đọc Từ Cache | Cache % | Đánh Giá |
|---|--------|----------|-------------|--------------|---------|----------|
{{#each cache_per_table}}
| {{@index}} | {{schemaname}} | **{{relname}}** | {{disk_reads}} | {{cache_hits}} | {{cache_hit_pct}}% | {{status_icon}} |
{{/each}}

**Quy ước:**
- ✅ Tốt: > 90% | 🟡 Trung bình: 70-90% | 🟠 Cao: 50-70% | 🔴 Nghiêm trọng: < 50%

---

## 4. TOP 20 TRUY VẤN CHẬM NHẤT

{{#if has_pg_stat_statements}}
| # | Mã Truy Vấn | Số Lần Gọi | TB (ms) | Cao Nhất (ms) | Tổng (ms) | Số Dòng |
|---|-------------|------------|---------|--------------|-----------|---------|
{{#each slow_queries}}
| {{@index}} | {{queryid}} | {{calls}} | {{avg_time_ms}} | {{max_time_ms}} | {{total_time_ms}} | {{rows}} |
{{/each}}

{{#each slow_queries}}
<details>
<summary>🔍 #{{@index}} — <code>{{main_table}}</code> — TB: {{avg_time_ms}}ms — {{calls}} lần gọi — {{rows}} dòng</summary>

```sql
{{query_full}}
```

| Chỉ Số | Giá Trị |
|--------|---------|
| **Mã truy vấn** | `{{queryid}}` |
| **Bảng chính** | `{{main_table}}` |
| **Thời gian trung bình** | {{avg_time_ms}} ms |
| **Thời gian cao nhất** | {{max_time_ms}} ms |
| **Tổng thời gian** | {{total_time_ms}} ms |
| **Số lần gọi** | {{calls}} |
| **Số dòng trả về** | {{rows}} |

{{#if has_solution}}
➡️ **Xem giải pháp:** [PERFORMANCE_SOLUTIONS.md](./PERFORMANCE_SOLUTIONS.md#{{solution_anchor}})
{{/if}}

</details>

{{/each}}
{{else}}
> ⚠️ Extension `pg_stat_statements` chưa được cài đặt. Không thể thu thập thông tin truy vấn chậm.
> Để cài đặt: `CREATE EXTENSION pg_stat_statements;` và thêm vào `shared_preload_libraries`.
{{/if}}

---

## 5. KÍCH THƯỚC BẢNG (Top 20)

| # | Schema | Tên Bảng | Tổng Dung Lượng | Dữ Liệu | Index | Số Dòng |
|---|--------|----------|-----------------|----------|-------|---------|
{{#each table_sizes}}
| {{@index}} | {{schemaname}} | **{{table_name}}** | {{total_size}} | {{data_size}} | {{index_size}} | {{row_count}} |
{{/each}}

---

## 6. BẢNG CẦN TẠO INDEX

| # | Schema | Tên Bảng | Seq Scan | Số Dòng Đọc Tuần Tự | Idx Scan | Số Dòng | Tỷ Lệ Seq % |
|---|--------|----------|----------|---------------------|----------|---------|-------------|
{{#each missing_indexes}}
| {{@index}} | {{schemaname}} | **{{relname}}** | {{seq_scan}} | {{seq_tup_read}} | {{idx_scan}} | {{n_live_tup}} | {{seq_scan_pct}}% |
{{/each}}

**Khuyến nghị:** Tạo index cho các bảng có tỷ lệ Seq Scan > 50% và số dòng > 10,000.

---

## 7. PHÂN TÍCH INDEX

### 7.1 Index Ít Sử Dụng Nhất (Top 20)

| # | Schema | Tên Bảng | Tên Index | Số Lần Dùng | Dung Lượng |
|---|--------|----------|-----------|-------------|------------|
{{#each least_used_indexes}}
| {{@index}} | {{schemaname}} | {{table_name}} | {{index_name}} | {{times_used}} | {{index_size}} |
{{/each}}

### 7.2 Index Không Sử Dụng (Nên Xem Xét Xóa)

| # | Schema | Tên Bảng | Tên Index | Dung Lượng |
|---|--------|----------|-----------|------------|
{{#each unused_indexes}}
| {{@index}} | {{schemaname}} | {{table_name}} | {{index_name}} | {{index_size}} |
{{/each}}

**Tổng dung lượng lãng phí bởi index không dùng:** {{total_unused_index_size}}

---

## 8. TRUY VẤN BỊ CHẶN & CHẠY QUÁ LÂU

### 8.1 Truy Vấn Bị Chặn (Blocking)

{{#if has_blocking}}
| # | PID Bị Chặn | Người Dùng | PID Đang Chặn | Người Dùng |
|---|-------------|-----------|--------------|-----------|
{{#each blocking_queries}}
| {{@index}} | {{blocked_pid}} | {{blocked_user}} | {{blocking_pid}} | {{blocking_user}} |
{{/each}}

{{#each blocking_queries}}
<details>
<summary>⛔ Blocking #{{@index}} — PID {{blocked_pid}} bị chặn bởi PID {{blocking_pid}}</summary>

**Truy vấn bị chặn (PID {{blocked_pid}}):**
```sql
{{blocked_query}}
```

**Truy vấn đang chặn (PID {{blocking_pid}}):**
```sql
{{blocking_query}}
```

**Gợi ý xử lý:**
```sql
-- Hủy truy vấn đang chặn (ưu tiên dùng cancel trước terminate)
SELECT pg_cancel_backend({{blocking_pid}});
-- Nếu không hiệu quả:
SELECT pg_terminate_backend({{blocking_pid}});
```

</details>

{{/each}}
{{else}}
✅ Không có truy vấn bị chặn tại thời điểm kiểm tra.
{{/if}}

### 8.2 Truy Vấn Chạy Quá Lâu (> 5 phút)

{{#if has_long_running}}
| # | PID | Người Dùng | Trạng Thái | Thời Gian |
|---|-----|-----------|------------|-----------|
{{#each long_running_queries}}
| {{@index}} | {{pid}} | {{usename}} | {{state}} | {{duration}} |
{{/each}}

{{#each long_running_queries}}
<details>
<summary>🕐 Long-running #{{@index}} — PID {{pid}} — {{duration}}</summary>

```sql
{{query_preview}}
```

**Gợi ý xử lý:**
```sql
SELECT pg_cancel_backend({{pid}});
```

</details>

{{/each}}
{{else}}
✅ Không có truy vấn chạy quá lâu tại thời điểm kiểm tra.
{{/if}}

---

## 9. DỮ LIỆU RÁC & TÌNH TRẠNG VACUUM

| # | Schema | Tên Bảng | Dòng Sống | Dòng Chết | Tỷ Lệ Chết % | Vacuum Cuối | Autovacuum Cuối |
|---|--------|----------|-----------|-----------|--------------|-------------|-----------------|
{{#each dead_tuples}}
| {{@index}} | {{schemaname}} | **{{relname}}** | {{n_live_tup}} | {{n_dead_tup}} | {{dead_pct}}% | {{last_vacuum}} | {{last_autovacuum}} |
{{/each}}

**Khuyến nghị:** Chạy `VACUUM ANALYZE` trên các bảng có tỷ lệ dòng chết > 20%.

---

## 10. TÌNH TRẠNG NHÂN BẢN (REPLICATION)

{{#if has_replication}}
| Máy Khách | Trạng Thái | Sent LSN | Write LSN | Replay LSN | Độ Trễ (bytes) |
|-----------|-----------|----------|-----------|------------|----------------|
{{#each replication_status}}
| {{client_addr}} | {{state}} | {{sent_lsn}} | {{write_lsn}} | {{replay_lsn}} | {{replication_lag_bytes}} |
{{/each}}
{{else}}
ℹ️ Không có nhân bản (replication) được cấu hình.
{{/if}}

---

## 11. TỔNG KẾT & KHUYẾN NGHỊ

> ⭐ Xem giải pháp cụ thể cho mỗi vấn đề: [PERFORMANCE_SOLUTIONS.md](./PERFORMANCE_SOLUTIONS.md)

### 🔴 Vấn Đề Nghiêm Trọng (P0)
{{#each critical_issues}}
- [ ] {{this}} → **[Xem Giải Pháp](./PERFORMANCE_SOLUTIONS.md#p0-{{@index}}-{{anchor}})**
{{/each}}

### 🟡 Cần Cải Thiện (P1)
{{#each warnings}}
- [ ] {{this}} → **[Xem Giải Pháp](./PERFORMANCE_SOLUTIONS.md#p1-{{@index}}-{{anchor}})**
{{/each}}

### 🟠 Nên Xử Lý (P2)
{{#each medium_issues}}
- [ ] {{this}}
{{/each}}

### ✅ Tình Trạng Tốt
{{#each good_status}}
- [x] {{this}}
{{/each}}

### Tóm Tắt Giải Pháp

```
Tổng giải pháp:       {{total_solutions}}
P0 Nghiêm trọng:      {{p0_count}} (xử lý trong 24h)
P1 Ưu tiên cao:       {{p1_count}} (xử lý trong 1 tuần)
P2 Trung bình:        {{p2_count}} (xử lý trong 1 tháng)
Script sẵn sàng chạy: {{script_count}} SQL scripts
```

---

*Báo cáo được tạo tự động bởi db-report-generator v3.0.0*
*Thời gian tạo: {{generated_at}}*
