# Dockerfile for Publisher Service
FROM python:3.11-slim

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser main.py .

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV TARGET_URL=http://aggregator:8080/publish
ENV NUM_EVENTS=20000
ENV DUPLICATE_RATE=0.30
ENV BATCH_SIZE=100
ENV DELAY_BETWEEN_BATCHES=0.1

# Run application
CMD ["python", "main.py"]
