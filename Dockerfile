# Multi-stage build for production optimization
FROM python:3.12-slim AS builder

# Install system dependencies for building (including PostgreSQL libraries)
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY app/ ./app/
COPY main.py ./
COPY uv.lock* ./

# Install dependencies
RUN uv sync

# Production stage
FROM python:3.12-slim AS production

# Install runtime dependencies for PostgreSQL
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy uv binary from builder stage
COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv

# Copy installed packages and virtual environment from builder stage
COPY --from=builder /app /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /app/.venv/bin/python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["/app/.venv/bin/python", "main.py"]
