FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install xray-core
ARG XRAY_VERSION=26.7.11
RUN wget -q "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip" -O /tmp/xray.zip \
    && unzip /tmp/xray.zip -d /usr/local/bin/ xray \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

VOLUME /data
CMD ["python", "-m", "src.main"]
