FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py portainer_sync.py demo_data.py ./
COPY templates ./templates

VOLUME ["/data"]
ENV DB_PATH=/data/homelab.db
EXPOSE 5000

CMD ["python3", "app.py"]
