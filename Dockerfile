# Dockerfile

# ── Stage 1: builder — install dependencies ────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dan install requirements terlebih dahulu (layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: production — image final yang ringan ─────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Copy installed packages dari builder
COPY --from=builder /install /usr/local

# Copy source code
COPY app/        ./app/
COPY pipeline/   ./pipeline/
COPY services/   ./services/
COPY db/         ./db/

# Buat direktori uploads
RUN mkdir -p /app/uploads

# Non-root user untuk keamanan
RUN useradd -m -u 1000 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Gunakan uvicorn dengan workers sesuai CPU
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]


# ── Stage 3: development — dengan hot-reload ──────────────────────────────
FROM production AS development

USER root
RUN pip install --no-cache-dir watchfiles
USER appuser

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-dir", "/app"]