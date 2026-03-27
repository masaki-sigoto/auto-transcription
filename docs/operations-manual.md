# 自動文字起こしツール 運用マニュアル

## 目次

1. [システム概要](#システム概要)
2. [アーキテクチャ](#アーキテクチャ)
3. [デプロイメント](#デプロイメント)
4. [監視・アラート](#監視アラート)
5. [バックアップ・リストア](#バックアップリストア)
6. [トラブルシューティング](#トラブルシューティング)
7. [セキュリティ](#セキュリティ)
8. [スケーリング](#スケーリング)

---

## システム概要

### 機能一覧

| 機能 | 説明 |
|------|------|
| 音声文字起こし | Whisperによる高精度な音声認識 |
| 話者分離 | 複数話者の自動識別 |
| LLM補正 | GPT-4による文脈を考慮した補正 |
| リアルタイム処理 | WebSocketによるリアルタイム文字起こし |
| チーム機能 | 共有・コメント・コラボレーション |
| 外部連携 | Slack、Notion、Google Drive等 |

### 技術スタック

- **バックエンド**: Python 3.11, FastAPI, Celery
- **フロントエンド**: React, TypeScript, Vite
- **データベース**: PostgreSQL 15
- **キャッシュ**: Redis 7
- **文字起こし**: OpenAI Whisper
- **インフラ**: Kubernetes (EKS), Terraform

---

## アーキテクチャ

### システム構成図

```
                    ┌─────────────┐
                    │   CloudFront│
                    │     (CDN)   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
        │  Frontend │ │   API   │ │  Worker   │
        │  (Nginx)  │ │ Gateway │ │  (Celery) │
        └───────────┘ └────┬────┘ └─────┬─────┘
                           │            │
                    ┌──────▼──────┐     │
                    │   Backend   │◄────┘
                    │  (FastAPI)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
        │ PostgreSQL│ │  Redis  │ │    S3     │
        │           │ │         │ │ (Storage) │
        └───────────┘ └─────────┘ └───────────┘
```

### コンポーネント説明

| コンポーネント | 役割 | レプリカ数 |
|--------------|------|-----------|
| Frontend | 静的ファイル配信 | 2-5 |
| Backend | API処理 | 3-10 |
| Worker | 文字起こし処理 | 2-20 |
| PostgreSQL | データ永続化 | 1 (Multi-AZ) |
| Redis | キャッシュ・キュー | 1 |

---

## デプロイメント

### 前提条件

- AWS CLI設定済み
- kubectl設定済み
- Terraform v1.0以上
- Docker

### 初期セットアップ

```bash
# 1. Terraformでインフラ構築
cd deploy/terraform
terraform init
terraform plan -var-file=production.tfvars
terraform apply -var-file=production.tfvars

# 2. kubeconfigの取得
aws eks update-kubeconfig --name transcription-app-eks --region ap-northeast-1

# 3. Kubernetesリソースの適用
cd ../kubernetes
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml  # 事前に値を設定
kubectl apply -f configmap.yaml
kubectl apply -f service-account.yaml
kubectl apply -f network-policy.yaml
kubectl apply -f postgres-statefulset.yaml
kubectl apply -f redis-statefulset.yaml
kubectl apply -f backend-deployment.yaml
kubectl apply -f frontend-deployment.yaml
kubectl apply -f worker-deployment.yaml
kubectl apply -f ingress.yaml
```

### デプロイ手順

```bash
# 通常のデプロイ（GitHub Actionsが自動実行）
git tag v1.2.3
git push origin v1.2.3

# 手動デプロイ
kubectl set image deployment/backend \
  backend=<ECR_URL>/backend:v1.2.3 \
  -n transcription-app

# ロールバック
kubectl rollout undo deployment/backend -n transcription-app
```

### 環境変数

| 変数名 | 説明 | 必須 |
|-------|------|------|
| DATABASE_URL | PostgreSQL接続文字列 | ✓ |
| REDIS_URL | Redis接続文字列 | ✓ |
| JWT_SECRET_KEY | JWT署名キー | ✓ |
| OPENAI_API_KEY | OpenAI APIキー | ✓ |
| AWS_ACCESS_KEY_ID | AWSアクセスキー | ✓ |
| AWS_SECRET_ACCESS_KEY | AWSシークレットキー | ✓ |
| S3_BUCKET | S3バケット名 | ✓ |

---

## 監視・アラート

### メトリクス

**アプリケーションメトリクス**

- `transcription_jobs_total`: 文字起こしジョブ総数
- `transcription_duration_seconds`: 処理時間
- `api_request_duration_seconds`: APIレスポンス時間
- `celery_queue_length`: Celeryキュー長

**インフラメトリクス**

- CPU使用率
- メモリ使用率
- ディスク使用率
- ネットワークI/O

### アラート設定

| アラート | 条件 | 重大度 |
|---------|------|-------|
| High CPU | CPU > 80% (5分間) | Warning |
| High Memory | Memory > 85% (5分間) | Warning |
| API Latency | p99 > 2秒 | Warning |
| Error Rate | エラー率 > 1% | Critical |
| Queue Backlog | キュー長 > 100 | Warning |
| Pod Down | レプリカ < 最小値 | Critical |

### ログ

```bash
# Podログの確認
kubectl logs -f deployment/backend -n transcription-app

# 特定のPodログ
kubectl logs <pod-name> -n transcription-app --tail=100

# 複数コンテナのログ
kubectl logs <pod-name> -c <container-name> -n transcription-app
```

---

## バックアップ・リストア

### PostgreSQLバックアップ

```bash
# 手動バックアップ
kubectl exec -it postgres-0 -n transcription-app -- \
  pg_dump -U transcription transcription > backup.sql

# S3へ保存
aws s3 cp backup.sql s3://transcription-app-backups/$(date +%Y%m%d)/
```

### リストア手順

```bash
# 1. メンテナンスモードに切り替え
kubectl scale deployment/backend --replicas=0 -n transcription-app
kubectl scale deployment/worker --replicas=0 -n transcription-app

# 2. データベースリストア
kubectl exec -it postgres-0 -n transcription-app -- \
  psql -U transcription -d transcription < backup.sql

# 3. サービス再開
kubectl scale deployment/backend --replicas=3 -n transcription-app
kubectl scale deployment/worker --replicas=2 -n transcription-app
```

### 自動バックアップ

- RDS自動バックアップ: 7日間保持
- S3バージョニング: 有効
- Glacierへの移行: 90日後

---

## トラブルシューティング

### よくある問題

#### 1. 文字起こしが進まない

```bash
# Workerの状態確認
kubectl get pods -l component=worker -n transcription-app

# Celeryキューの確認
kubectl exec -it <worker-pod> -n transcription-app -- \
  celery -A app.worker inspect active

# Redisの確認
kubectl exec -it redis-0 -n transcription-app -- redis-cli LLEN celery
```

#### 2. APIが遅い

```bash
# 接続数の確認
kubectl exec -it postgres-0 -n transcription-app -- \
  psql -U transcription -c "SELECT count(*) FROM pg_stat_activity"

# スロークエリの確認
kubectl exec -it postgres-0 -n transcription-app -- \
  psql -U transcription -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10"
```

#### 3. Podが起動しない

```bash
# イベントの確認
kubectl describe pod <pod-name> -n transcription-app

# リソース状況の確認
kubectl top pods -n transcription-app
kubectl top nodes
```

### ログ調査

```bash
# エラーログの検索
kubectl logs deployment/backend -n transcription-app | grep ERROR

# 特定時間帯のログ
kubectl logs deployment/backend -n transcription-app --since=1h
```

---

## セキュリティ

### 認証・認可

- JWT認証（有効期限: 24時間）
- リフレッシュトークン（有効期限: 7日）
- APIキー認証（開発者向け）

### ネットワークセキュリティ

- VPC内プライベートサブネット
- Network Policy によるPod間通信制御
- WAFによる攻撃防御

### データ保護

- 転送中暗号化: TLS 1.3
- 保存時暗号化: AES-256
- 機密データ: AWS Secrets Manager

### セキュリティチェックリスト

- [ ] シークレットのローテーション（90日ごと）
- [ ] 脆弱性スキャン（週次）
- [ ] アクセスログの監査（月次）
- [ ] ペネトレーションテスト（年次）

---

## スケーリング

### 自動スケーリング

**HPA設定**

| コンポーネント | 最小 | 最大 | CPU閾値 |
|--------------|------|------|---------|
| Backend | 3 | 10 | 70% |
| Frontend | 2 | 5 | 70% |
| Worker | 2 | 20 | キュー長 |

### 手動スケーリング

```bash
# レプリカ数の変更
kubectl scale deployment/backend --replicas=5 -n transcription-app
kubectl scale deployment/worker --replicas=10 -n transcription-app
```

### GPUワーカーの追加

```bash
# GPUノードの追加（Terraform）
cd deploy/terraform
terraform apply -var="gpu_node_count=5"
```

---

## 連絡先

| 役割 | 連絡先 |
|------|-------|
| インフラ担当 | infra@example.com |
| アプリ担当 | app@example.com |
| セキュリティ | security@example.com |
| 緊急連絡 | oncall@example.com |

## 更新履歴

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2024-01-01 | 1.0.0 | 初版作成 |
