FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY cairn ./cairn
RUN pip install --no-cache-dir ".[server]"
ENV CAIRN_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8000/health')"
CMD ["cairn", "serve", "--host", "0.0.0.0", "--port", "8000"]
