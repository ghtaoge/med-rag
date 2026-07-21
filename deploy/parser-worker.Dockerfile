FROM python:3.13-slim

WORKDIR /app

RUN groupadd --gid 10001 parser \
    && useradd --uid 10001 --gid 10001 --no-create-home parser \
    && mkdir -p /data/quarantine /data/original /data/parsed /data/temporary /models \
    && chown -R 10001:10001 /data/original /data/parsed /data/temporary

COPY deploy/parser-requirements.txt ./
COPY app/ app/
COPY config.yaml ./
RUN pip install --no-cache-dir -r parser-requirements.txt

USER 10001:10001

CMD ["rq", "worker", "--url", "redis://redis:6379/0", "med-rag-parse"]
