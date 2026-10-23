# Hugging Face Space (Docker): the API only. The code comes from the PUBLIC GitHub repository; the built data (legal store and search
# indexes, derived from FBR documents) is NOT here: start.py downloads it from a PRIVATE dataset with a read token kept as a Space secret.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 FASTEMBED_CACHE_PATH=/home/user/.fastembed
WORKDIR /home/user/app
# changes whenever main moves, so a rebuild always takes the newest code
ADD https://api.github.com/repos/Maaz5711/customs-copilot/git/refs/heads/main /tmp/main-ref.json
RUN git clone --depth 1 --branch main https://github.com/Maaz5711/customs-copilot.git .
RUN pip install --no-cache-dir -r requirements.txt huggingface_hub
# fetch the two small local models at build time so a cold start only has to load them
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"
ENV API_HOST=0.0.0.0 API_PORT=7860 TRUST_PROXY=1 API_HSTS=1 LLM_PROVIDER=deepseek
EXPOSE 7860
CMD ["python", "deploy/hf-space/start.py"]
