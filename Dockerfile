FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN pip install uv

RUN uv sync --frozen

COPY . .

RUN mkdir -p cache

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "main.py", "--server.address", "0.0.0.0"]
