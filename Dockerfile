FROM python:3.12-slim

WORKDIR /app

ARG APP_VERSION=dev
ARG APP_COMMIT=local

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/
RUN python -c "from pathlib import Path; v='''${APP_VERSION}'''; c='''${APP_COMMIT}'''[:8]; [p.write_text(p.read_text(encoding='utf-8').replace('__APP_VERSION__', v).replace('__APP_COMMIT_SHORT__', c), encoding='utf-8') for p in Path('frontend/dist').glob('*.html')]"

RUN mkdir -p /data /logs

ENV DATA_DIR=/data
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
