FROM python

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

EXPOSE 8501

# Chaining: Run the pipeline, AND IF it succeeds, run the app
CMD python pipeline_runner.py && streamlit run app.py --server.port=8501 --server.address=0.0.0.0