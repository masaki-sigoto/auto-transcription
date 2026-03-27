#!/bin/bash

# ===========================================
# 自動文字起こしツール 起動スクリプト
# ===========================================

set -e

echo "=========================================="
echo "  自動文字起こしツール"
echo "=========================================="
echo ""

# .envファイルの確認
if [ ! -f .env ]; then
    echo "警告: .envファイルが見つかりません"
    echo ".env.example をコピーして .env を作成してください"
    echo ""
    cp .env.example .env 2>/dev/null || echo ".env.example も見つかりません"
fi

# Docker Composeで起動
echo "Dockerコンテナを起動しています..."
echo ""

docker compose up --build -d

echo ""
echo "=========================================="
echo "  起動完了!"
echo "=========================================="
echo ""
echo "アクセスURL:"
echo "  - フロントエンド: http://localhost:3001"
echo "  - バックエンドAPI: http://localhost:8001"
echo "  - APIドキュメント: http://localhost:8001/docs"
echo ""
echo "ログを確認するには:"
echo "  docker compose logs -f"
echo ""
echo "停止するには:"
echo "  docker compose down"
echo ""
