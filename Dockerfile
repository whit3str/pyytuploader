FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY youtube_uploader.py .

# Create a volume for persistent storage
VOLUME ["/app/data", "/app/videos"]

# Create necessary directories
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application with data directory
CMD ["python", "youtube_uploader.py", "--folder", "/app/videos"]