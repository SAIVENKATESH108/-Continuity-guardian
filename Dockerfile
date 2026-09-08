# Dockerfile for Continuity Guardian API
# Compatible with Google Cloud Run, Hugging Face Spaces, and local Docker

FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python package dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY agent/ ./agent/
COPY api/ ./api/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create a non-root user for security (required by Hugging Face Spaces)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port (Cloud Run overrides via $PORT, Hugging Face via 7860)
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0 and the dynamically assigned $PORT
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
