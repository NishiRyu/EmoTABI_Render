#!/bin/bash
set -e

# プロダクション用環境変数設定
export FLASK_ENV=production
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

echo "=== EMOTABI Production Startup ==="
echo "Environment: $FLASK_ENV"
echo "PORT: $PORT"
echo "Working Directory: $(pwd)"

# ポート設定（Renderに最適化）
FINAL_PORT=${PORT:-10000}
echo "Using port: $FINAL_PORT"

# 必要なディレクトリ作成（chartsは不要）
echo "Creating required directories..."
mkdir -p static/uploads static/images static/css static/js
chmod 755 static/uploads

# アプリケーションの存在確認
if [ ! -f "app.py" ]; then
    echo "ERROR: app.py not found!"
    exit 1
fi

# テンプレートディレクトリの確認
if [ ! -d "templates" ]; then
    echo "ERROR: templates directory not found!"
    exit 1
fi

echo "All checks passed. Starting Gunicorn server..."

# プロダクション用Gunicorn設定
exec gunicorn \
    --bind 0.0.0.0:$FINAL_PORT \
    --workers 2 \
    --worker-class sync \
    --worker-connections 1000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    app:app 