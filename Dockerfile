FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && \
    useradd -u 10001 -m invoiceflow && \
    mkdir -p /data && chown invoiceflow:invoiceflow /data
USER invoiceflow
ENV IF_DB_PATH=/data/invoiceflow.sqlite
EXPOSE 8000
CMD ["uvicorn","invoiceflow.api:app","--host","0.0.0.0","--port","8000"]
