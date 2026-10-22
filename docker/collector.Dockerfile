FROM python:3.12-slim
WORKDIR /app
# instagrapi é OPCIONAL e roda isolado; não é serviço permanente nem parte do site.
COPY etl/requirements-collector.txt /tmp/requirements-collector.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-collector.txt
COPY etl/ ./etl/
ENTRYPOINT ["python"]
