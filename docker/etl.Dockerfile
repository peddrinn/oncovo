FROM python:3.12-slim
WORKDIR /app
COPY etl/ ./etl/
ENTRYPOINT ["python"]
