FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY youtube_uploader.py .

# Create volumes for persistent storage
VOLUME ["/app/data", "/app/videos"]

# Create necessary directories
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV YTU_VIDEOS_FOLDER="/app/videos"
ENV YTU_PRIVACY_STATUS="private"
ENV YTU_CHECK_INTERVAL="60"
ENV YTU_CLIENT_SECRETS="/app/data/client_secrets.json"

# Run the application
CMD ["python", "youtube_uploader.py"]