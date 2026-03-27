# Development Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsndfile1 \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./

# Install with pip (simpler than Poetry for Docker)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    "uvicorn[standard]>=0.27.0" \
    python-multipart>=0.0.6 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    sqlalchemy>=2.0.25 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.0 \
    alembic>=1.13.0 \
    redis>=5.0.0 \
    celery>=5.3.0 \
    boto3>=1.34.0 \
    httpx>=0.26.0 \
    "python-jose[cryptography]>=3.3.0" \
    "passlib[bcrypt]>=1.7.4" \
    pydub>=0.25.1 \
    ffmpeg-python>=0.2.0 \
    anthropic>=0.18.0 \
    websockets>=12.0 \
    librosa>=0.10.0 \
    scikit-learn>=1.4.0 \
    python-docx>=1.1.0 \
    numpy \
    email-validator

# Install PyTorch (CPU version for smaller image)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install Whisper (faster-whisper for efficiency)
RUN pip install --no-cache-dir faster-whisper>=1.0.0

# Create storage directory
RUN mkdir -p /app/storage && chmod 777 /app/storage

# Copy application code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
