# Reason: Multi-stage build to minimize final image size
# Stage 1: Build stage with uv for dependency installation
FROM python:3.11-slim AS builder

# Install uv package manager
# Reason: uv is significantly faster than pip and handles dependency resolution better
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer caching
# Reason: Dependencies change less frequently than source code
COPY pyproject.toml uv.lock README.md ./

# Export dependencies and install to system Python
# Reason: Export lock file to requirements.txt format, then install with pip
RUN uv export --no-dev --no-hashes -o requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt && \
    rm requirements.txt

# Stage 2: Runtime stage with minimal footprint
FROM python:3.11-slim

# Reason: OCI labels provide metadata for container registries
LABEL org.opencontainers.image.title="Citeo" \
      org.opencontainers.image.description="arXiv RSS订阅 + AI摘要翻译 + 多渠道推送系统" \
      org.opencontainers.image.source="https://github.com/fjhdream/citeo" \
      org.opencontainers.image.url="https://github.com/fjhdream/citeo" \
      org.opencontainers.image.documentation="https://github.com/fjhdream/citeo#readme" \
      org.opencontainers.image.licenses="MIT"

# Install runtime dependencies for PDF processing
# Reason: pymupdf requires additional system libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libmupdf-dev \
    mupdf-tools \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
# Reason: Never run containers as root
RUN useradd -m -u 1000 citeo && \
    mkdir -p /app/data && \
    chown -R citeo:citeo /app

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY --chown=citeo:citeo src/ ./src/
COPY --chown=citeo:citeo scripts/ ./scripts/
COPY --chown=citeo:citeo pyproject.toml README.md ./

# Switch to non-root user
USER citeo

# Set PYTHONPATH to include src directory
# Reason: citeo package is in src/ directory
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Expose API port
EXPOSE 8000

# Health check
# Reason: Allow container orchestration to verify service health
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)" || exit 1

# Default command: start API server with scheduler
CMD ["python", "-m", "citeo.main"]
