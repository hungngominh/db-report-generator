FROM python:3.11-slim

WORKDIR /app

COPY services/db-monitor/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY .agents/skills/db-report-generator/scripts ./scripts
COPY services/db-monitor/monitor ./monitor
COPY services/db-monitor/storage ./storage

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "monitor.main"]
