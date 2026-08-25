FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY handler.py /app/handler.py

CMD ["python", "-u", "/app/handler.py"]
