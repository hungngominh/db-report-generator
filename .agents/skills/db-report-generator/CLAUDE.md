Read SKILL.md for the full instructions on how this skill works.

## Quy Tắc Quan Trọng

### ⛔ Query Text: KHÔNG nhét vào table — dùng `<details>`
**Đây là lỗi đã xảy ra NHIỀU LẦN. KHÔNG ĐƯỢC bỏ qua.**

Query text (slow queries, blocking queries, long-running queries) **KHÔNG BAO GIỜ** nằm trong markdown table cell. Luôn bị vỡ bảng.

**Cách đúng duy nhất:**
1. Bảng chỉ chứa **số liệu** (calls, avg_ms, max_ms, rows...)
2. Query text nằm trong `<details>` expandable bên dưới bảng
3. Summary hiển thị: `#index — tên_bảng — TB: xxxms — N lần gọi — M dòng`

```markdown
<details>
<summary>🔍 #1 — <code>dbo.OrderVehicle</code> — TB: 9640ms — 4 lần gọi</summary>

\`\`\`sql
SELECT ... (giữ nguyên format gốc)
\`\`\`

</details>
```

### Sanitize mọi cell khác trong table
```python
import re
def sanitize(value):
    if value is None:
        return ""
    s = str(value)
    s = s.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    s = s.replace('|', '\\|')
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()
```
Dùng cho: table names, index names, số liệu, MỌI giá trị từ DB đưa vào table.

### Extract tên bảng từ query
Dùng `extract_table_name(query)` để parse tên bảng chính từ FROM/JOIN/UPDATE/INTO. Hiển thị trong `<summary>` của details.

### Thư mục làm việc
- **KHÔNG ĐƯỢC** tạo script ở thư mục hệ thống (C:\...\Temp, /tmp, scratchpad)
- **PHẢI** tạo tại `{workspace}/.scripts/generate_db_report.py`

### pg_stat_statements
- **LUÔN** detect schema trước khi query (Bước 3.4a trong SKILL.md)
- Dùng schema-qualified: `{ext_schema}.pg_stat_statements`
- Detect PG version cho tên cột (>= 13 vs < 13)

### Ngôn ngữ
- Báo cáo bằng **tiếng Việt**
- Giữ tiếng Anh: tên bảng DB, SQL code, code snippets, tên file

### Format số
- Dấu phẩy hàng nghìn: `4,047,511`
- Phần trăm 2 chữ số: `26.91%`
- Dung lượng: MB, GB, kB
