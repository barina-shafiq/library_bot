# Use official slim Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Set working directory
WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create a non-root user with UID 1000 (Hugging Face Spaces standard)
# and give ownership of /app to ensure SQLite write access
RUN useradd -m -u 1000 user && \
    chown -R user:user /app

USER user

# Seed SQLite database
RUN python database.py

# Expose default Hugging Face Spaces port
EXPOSE 7860

# Run with Gunicorn on port 7860
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
