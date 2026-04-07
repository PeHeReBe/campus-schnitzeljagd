FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN mkdir -p /data /logs

ENV DATA_DIR=/data
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
