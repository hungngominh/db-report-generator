# Tests

## Chạy nhanh (thuần Python, không cần DB)
```bash
cd .agents/skills/db-report-generator
pip install -r requirements-dev.txt
python -m pytest -q
```

## Cập nhật golden khi render đổi có chủ đích
```bash
UPDATE_GOLDEN=1 python -m pytest tests/unit/test_render.py -q
```

## Unit-collector matrix (P0+ , cần Docker)
```bash
docker compose -f docker-compose.pg.yml up -d
# ... chạy test collector trỏ tới cổng 55432..55436 ...
docker compose -f docker-compose.pg.yml down
```

CI cloud: `.github/workflows/tests.yml` (template, dùng khi repo có remote).
