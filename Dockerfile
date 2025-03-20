FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Create necessary directories
RUN mkdir -p /app/data/processed

# Add wait-for-qdrant script
RUN echo '#!/bin/sh\n\
while ! echo > /dev/tcp/algernon-qdrant/6333; do\n\
  echo "Waiting for Qdrant to be ready..."\n\
  sleep 1\n\
done\n\
echo "Qdrant is ready!"' > /app/wait-for-qdrant.sh && \
chmod +x /app/wait-for-qdrant.sh

# Expose Streamlit port
EXPOSE 8501

# Run the application
CMD ["streamlit", "run", "src/app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"] 