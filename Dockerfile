# -------------------------
#   Dockerfile
# -------------------------

FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose API + Streamlit ports
EXPOSE 8000
EXPOSE 8501

# Default command: run API
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
