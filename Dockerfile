FROM python:3.12-slim

WORKDIR /app

ARG APP_VERSION=dev
ARG APP_COMMIT=local

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/
RUN SHORT_COMMIT="$(printf '%s' "$APP_COMMIT" | cut -c1-8)" && \
    find ./frontend/dist -type f -name "*.html" -exec sed -i \
      -e "s/__APP_VERSION__/${APP_VERSION}/g" \
      -e "s/__APP_COMMIT_SHORT__/${SHORT_COMMIT}/g" \
      {} +

RUN mkdir -p /data /logs

ENV DATA_DIR=/data
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
