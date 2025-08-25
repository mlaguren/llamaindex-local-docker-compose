FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# If requirements.txt already pins ray==2.38.0, this is enough:
RUN pip install --no-cache-dir -r requirements.txt

# OR, if you prefer to force-match regardless of the file, add:
# RUN pip install --no-cache-dir "ray[default]==2.38.0" "grpcio>=1.58"

# Optional: verify at build
RUN python - <<'PY'
import ray
print(">> Build-time ray.__version__:", ray.__version__)
PY

COPY . .

EXPOSE 8000
# Keep a single worker (good for Ray client init)
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--loop","asyncio"]
