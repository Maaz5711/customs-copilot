# Customs Copilot API for any container host (Google Cloud Run, Render, Koyeb, Fly.io, a VM). One process: the rate limiter and conversations live in memory,
# so run a single instance (Cloud Run: --max-instances 1).
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 FASTEMBED_CACHE_PATH=/app/.fastembed LLM_PROVIDER=deepseek PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt google-cloud-storage
# fetch the two small local models at build time so a cold start only has to load them
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"
COPY src ./src
COPY deploy ./deploy
COPY data/ground_truth ./data/ground_truth
# The legal store and search indexes are NOT in the image or in git: deploy/start.py downloads them at start-up from a private dataset (see docs/DEPLOY.md).
EXPOSE 8080
CMD ["python", "deploy/start.py"]
