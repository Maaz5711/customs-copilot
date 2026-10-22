# Customs Copilot API (FastAPI + the LangGraph agent). One process: the rate limiter and conversations live in memory.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 API_HOST=0.0.0.0 API_PORT=8000 TRUST_PROXY=1 API_HSTS=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
# The legal store and the search indexes are NOT in this image and NOT in git: build them from the official FBR PDFs
# (see docs/sources.md and README), then put data/processed/legal_store.sqlite and data/processed/search_index/ under /app/data/processed/
# (a mounted volume, or a private download at start-up). Set ALLOWED_HOSTS, DEEPSEEK_API_KEY (or another provider key) and API_MAX_LLM_CALLS as environment variables.
EXPOSE 8000
CMD ["python", "-m", "src.api"]
