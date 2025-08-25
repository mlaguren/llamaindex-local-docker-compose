FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "ray[default]==2.31.0"
EXPOSE 8265 10001 6379
CMD bash -lc "ray start --head \
  --dashboard-host=0.0.0.0 \
  --port=6379 \
  --ray-client-server-port=10001 \
  --dashboard-port=8265 \
  --temp-dir=/tmp/ray \
  --block"
