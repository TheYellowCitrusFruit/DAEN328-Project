FROM python:3.11-slim

# Install system dependencies for GeoPandas and OSMNX
RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# Use exec-form so the process receives OS signals directly (clean shutdown)
CMD ["/bin/sh", "-c", "python pipeline_runner.py && streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]