# ==============================================================================
# Production Dockerfile for Bulk Certificate Generation Platform
# ==============================================================================
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal system dependencies required for compilation and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root system user and dedicated storage directory
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -m appuser && \
    mkdir -p /app/storage/certificates /app/storage/tmp && \
    chown -R appuser:appgroup /app

# Copy application source code
COPY . /app/
RUN chown -R appuser:appgroup /app

# Switch to non-root execution context
USER appuser

EXPOSE 8000

# Default entry command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
