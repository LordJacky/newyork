FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install uv
RUN pip install uv

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Create cache directory
RUN mkdir -p cache

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD ["uv", "run", "streamlit", "run", "main.py", "--server.address", "0.0.0.0"]
