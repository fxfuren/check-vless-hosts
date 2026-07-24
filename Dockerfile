FROM python:3.12-slim

# Install latest stable xray-core
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*

RUN LATEST_TAG=$(wget -qO- https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r .tag_name) \
    && echo "Downloading Xray $LATEST_TAG" \
    && wget -q "https://github.com/XTLS/Xray-core/releases/download/${LATEST_TAG}/Xray-linux-64.zip" -O /tmp/xray.zip \
    && unzip /tmp/xray.zip -d /usr/local/bin/ xray \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

VOLUME /data
CMD ["python", "-m", "src.main"]
