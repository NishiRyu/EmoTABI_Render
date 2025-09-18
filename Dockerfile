# Python 3.11の公式イメージを使用
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# システムの依存関係をインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    libgl1-mesa-dri \
    libegl1-mesa \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libfontconfig1-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー
COPY . .

# start.shに実行権限を付与
RUN chmod +x /app/start.sh

# 必要なディレクトリを作成（chartsは不要）
RUN mkdir -p static/uploads \
    && chmod 755 static/uploads

# プロダクション用環境変数を設定
ENV FLASK_APP=app.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# ポートを公開
EXPOSE 10000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

# 起動スクリプトを実行
CMD ["/app/start.sh"]
    