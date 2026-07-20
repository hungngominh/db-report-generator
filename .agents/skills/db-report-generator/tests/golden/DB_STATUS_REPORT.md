# Báo cáo tình trạng Database

## Target: analytics (`t-analytics`) — thu thập: error

> 🔴 Lỗi thu thập: statement_timeout: không kết nối được trong 5s

## Target: app_prod (`t-main`) — thu thập: ok

> Cửa sổ lấy mẫu: 30s (2026-07-16T00:00:00Z → 2026-07-16T00:00:30Z)

### overview — ok

| Finding | Mức | Đánh giá | Tin cậy |
|---|---|---|---|
| `db.reachable` | info | 🟢 green | measured |

### query_workload — ok

| Finding | Mức | Đánh giá | Tin cậy |
|---|---|---|---|
| `query.high-total-time` | warning | 🟡 yellow | measured |

### wait_events — skipped · cần pg_read_all_stats

> ⚪ Sampling không hợp lệ — các đánh giá bị hạ về `unknown`.

### wraparound — ok · stats vừa reset giữa 2 mẫu

> ⚪ Sampling không hợp lệ — các đánh giá bị hạ về `unknown`.

| Finding | Mức | Đánh giá | Tin cậy |
|---|---|---|---|
| `xid.wraparound-age` | notice | ⚪ unknown | heuristic |
