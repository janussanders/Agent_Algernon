# Start from a suitable base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Accept build arguments
ARG SRC_DIR

# Install system dependencies and clean up in the same layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    iputils-ping \
    netcat-openbsd \
    dnsutils \
    net-tools \
    procps \
    iproute2 \
    telnet \
    traceroute \
    mtr-tiny \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements and env files directly from project root
COPY requirements.txt /app/requirements.txt
COPY .env /app/.env

# Copy diagnostic script
COPY aws/docker/diagnose.sh /app/diagnose.sh
COPY aws/docker/start.sh /app/start.sh
RUN chmod +x /app/diagnose.sh /app/start.sh

# Install Python dependencies with cleanup
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && rm -rf ~/.cache/pip/*

# Copy the source code using arg
COPY ${SRC_DIR}/ /app/src/

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV QDRANT_HOST=qdrant
ENV QDRANT_HTTP_PORT=6333

# Create necessary directories
RUN mkdir -p /app/logs /app/data

# Set permissions
RUN chmod -R 777 /app/logs /app/data

# Expose ports
EXPOSE 8501 6333 6334

# Run the Streamlit application using the start script
CMD ["/app/start.sh"] 