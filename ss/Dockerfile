FROM python:3.11-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
COPY app ./app
COPY static ./static
RUN useradd -u 10001 -s /usr/sbin/nologin appuser
USER appuser
ENV DATA_DIR=/data HOME=/data

FROM base AS api
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1","--proxy-headers","--forwarded-allow-ips","*"]

FROM base AS worker-builder
USER root
# Official PaddlePaddle CPU installation channel. CPU-only Ubuntu x86-64 target.
RUN python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ && python -m pip install 'paddleocr>=3.3,<4'
USER appuser

FROM worker-builder AS worker
ENV OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
CMD ["python","-m","app.worker"]
