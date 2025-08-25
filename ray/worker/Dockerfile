FROM python:3.11-slim
RUN pip install --no-cache-dir "ray[default]==2.31.0"
CMD bash -lc "ray start --address=ray-head:6379 --block"
