FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps (keep slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ---- Install deps
# Make sure THIS requirements.txt is inside your build context (given compose uses context: ./app)
COPY requirements.txt ./requirements.txt

# Upgrade pip toolchain (harmless + helpful)
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip check

# Build-time sanity checks (fail early if missing)
RUN python - <<'PY'
import sys
print("Python:", sys.version)
import ray; print("ray:", ray.__version__)
import prometheus_fastapi_instrumentator as pfi
print("prometheus-fastapi-instrumentator present")
PY

# ---- App code last for better caching
COPY . .

EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--loop","asyncio"]
