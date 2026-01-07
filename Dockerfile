# Multi-stage build for Refresherr - Single Container
# Stage 1: Build React dashboard
FROM node:18-alpine AS dashboard-builder

WORKDIR /dashboard
COPY dashboard/package*.json ./
RUN npm ci --only=production
COPY dashboard/ ./
RUN npm run build

# Stage 2: Final unified container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy Python requirements and install dependencies
COPY app/requirements.txt /app/refresher-requirements.txt
COPY services/dashboard/requirements.txt /app/dashboard-requirements.txt
COPY services/research-relay/requirements.txt /app/relay-requirements.txt

RUN pip install --no-cache-dir \
    -r /app/refresher-requirements.txt \
    -r /app/dashboard-requirements.txt \
    -r /app/relay-requirements.txt

# Copy application code
COPY app/ /app/
COPY services/dashboard/app.py /app/dashboard_app.py
COPY services/dashboard/api.py /app/dashboard_api.py
COPY services/dashboard/templates /app/templates
COPY services/research-relay/app.py /app/relay_app.py

# Copy built React dashboard
COPY --from=dashboard-builder /dashboard/build /app/static

# Create entrypoint script
RUN cat > /app/entrypoint.sh <<'EOF'
#!/bin/bash
set -e

# Start relay service in background (internal, no external exposure needed)
echo "Starting relay service..."
python -c "from relay_app import app; app.run(host='127.0.0.1', port=5050)" &
RELAY_PID=$!

# Start dashboard/API service in background
echo "Starting dashboard API..."
python dashboard_app.py &
DASHBOARD_PID=$!

# Start scanner service in foreground
echo "Starting scanner..."
exec python -m cli run
EOF

RUN chmod +x /app/entrypoint.sh

# Expose dashboard port
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD curl -fsS http://localhost:8088/health || exit 1

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/entrypoint.sh"]
