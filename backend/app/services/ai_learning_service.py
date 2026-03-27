"""AI自動学習・カスタムモデルサービス"""

import os
import uuid
import json
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class ModelType(str, Enum):
    SPEECH_TO_TEXT = "speech_to_text"
    SPEAKER_DIARIZATION = "speaker_diarization"
    LANGUAGE_MODEL = "language_model"
    VOCABULARY = "vocabulary"
    ACOUSTIC = "acoustic"


class TrainingStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    TRAINING = "training"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetType(str, Enum):
    AUDIO_TRANSCRIPTION = "audio_transcription"
    TEXT_CORRECTION = "text_correction"
    VOCABULARY = "vocabulary"
    SPEAKER_SAMPLES = "speaker_samples"


@dataclass
class TrainingDataset:
    """学習データセット"""
    id: str
    name: str
    type: DatasetType
    tenant_id: str
    size_bytes: int
    sample_count: int
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    validation_split: float = 0.1


@dataclass
class CustomModel:
    """カスタムモデル"""
    id: str
    name: str
    type: ModelType
    tenant_id: str
    base_model: str
    version: str
    status: TrainingStatus
    created_at: datetime
    updated_at: datetime
    accuracy: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingJob:
    """学習ジョブ"""
    id: str
    model_id: str
    dataset_ids: List[str]
    status: TrainingStatus
    progress: float
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    hyperparameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedbackEntry:
    """ユーザーフィードバック"""
    id: str
    transcription_id: str
    user_id: str
    original_text: str
    corrected_text: str
    segment_start_ms: int
    segment_end_ms: int
    created_at: datetime
    applied: bool = False


class DatasetManager:
    """データセット管理"""

    def __init__(self):
        self._datasets: Dict[str, TrainingDataset] = {}
        self._dataset_samples: Dict[str, List[Dict[str, Any]]] = {}

    async def create_dataset(
        self,
        name: str,
        dataset_type: DatasetType,
        tenant_id: str,
    ) -> TrainingDataset:
        """データセットを作成"""
        dataset_id = str(uuid.uuid4())
        dataset = TrainingDataset(
            id=dataset_id,
            name=name,
            type=dataset_type,
            tenant_id=tenant_id,
            size_bytes=0,
            sample_count=0,
            created_at=datetime.utcnow(),
        )
        self._datasets[dataset_id] = dataset
        self._dataset_samples[dataset_id] = []
        return dataset

    async def add_samples(
        self,
        dataset_id: str,
        samples: List[Dict[str, Any]],
    ) -> int:
        """サンプルを追加"""
        if dataset_id not in self._datasets:
            raise ValueError("Dataset not found")

        self._dataset_samples[dataset_id].extend(samples)
        dataset = self._datasets[dataset_id]
        dataset.sample_count = len(self._dataset_samples[dataset_id])
        dataset.size_bytes += sum(len(json.dumps(s)) for s in samples)

        return len(samples)

    async def get_dataset(self, dataset_id: str) -> Optional[TrainingDataset]:
        """データセットを取得"""
        return self._datasets.get(dataset_id)

    async def list_datasets(self, tenant_id: str) -> List[TrainingDataset]:
        """テナントのデータセット一覧"""
        return [d for d in self._datasets.values() if d.tenant_id == tenant_id]

    async def delete_dataset(self, dataset_id: str) -> bool:
        """データセットを削除"""
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            del self._dataset_samples[dataset_id]
            return True
        return False

    async def export_for_training(
        self,
        dataset_id: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """学習用にエクスポート（train/val分割）"""
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise ValueError("Dataset not found")

        samples = self._dataset_samples.get(dataset_id, [])
        split_idx = int(len(samples) * (1 - dataset.validation_split))

        return samples[:split_idx], samples[split_idx:]


class CustomModelManager:
    """カスタムモデル管理"""

    def __init__(self):
        self._models: Dict[str, CustomModel] = {}
        self._training_jobs: Dict[str, TrainingJob] = {}

    async def create_model(
        self,
        name: str,
        model_type: ModelType,
        tenant_id: str,
        base_model: str = "whisper-large-v3",
        config: Optional[Dict[str, Any]] = None,
    ) -> CustomModel:
        """カスタムモデルを作成"""
        model_id = str(uuid.uuid4())
        now = datetime.utcnow()

        model = CustomModel(
            id=model_id,
            name=name,
            type=model_type,
            tenant_id=tenant_id,
            base_model=base_model,
            version="1.0.0",
            status=TrainingStatus.PENDING,
            created_at=now,
            updated_at=now,
            config=config or {},
        )

        self._models[model_id] = model
        return model

    async def get_model(self, model_id: str) -> Optional[CustomModel]:
        """モデルを取得"""
        return self._models.get(model_id)

    async def list_models(self, tenant_id: str) -> List[CustomModel]:
        """テナントのモデル一覧"""
        return [m for m in self._models.values() if m.tenant_id == tenant_id]

    async def start_training(
        self,
        model_id: str,
        dataset_ids: List[str],
        hyperparameters: Optional[Dict[str, Any]] = None,
    ) -> TrainingJob:
        """学習を開始"""
        model = self._models.get(model_id)
        if not model:
            raise ValueError("Model not found")

        job_id = str(uuid.uuid4())
        job = TrainingJob(
            id=job_id,
            model_id=model_id,
            dataset_ids=dataset_ids,
            status=TrainingStatus.PREPARING,
            progress=0.0,
            started_at=datetime.utcnow(),
            hyperparameters=hyperparameters or {
                "learning_rate": 1e-5,
                "batch_size": 16,
                "epochs": 10,
                "warmup_steps": 500,
            },
        )

        self._training_jobs[job_id] = job
        model.status = TrainingStatus.PREPARING
        model.updated_at = datetime.utcnow()

        # 非同期で学習を開始
        asyncio.create_task(self._run_training(job))

        return job

    async def _run_training(self, job: TrainingJob):
        """学習を実行（シミュレーション）"""
        try:
            model = self._models.get(job.model_id)
            if not model:
                return

            # 準備フェーズ
            job.status = TrainingStatus.PREPARING
            job.logs.append("Preparing training data...")
            await asyncio.sleep(1)

            # 学習フェーズ
            job.status = TrainingStatus.TRAINING
            model.status = TrainingStatus.TRAINING
            model.updated_at = datetime.utcnow()

            epochs = job.hyperparameters.get("epochs", 10)
            for epoch in range(epochs):
                job.progress = (epoch + 1) / epochs * 0.9  # 90%まで
                job.logs.append(f"Epoch {epoch + 1}/{epochs} completed")
                await asyncio.sleep(0.5)

            # 検証フェーズ
            job.status = TrainingStatus.VALIDATING
            job.logs.append("Validating model...")
            await asyncio.sleep(1)

            # 完了
            job.status = TrainingStatus.COMPLETED
            job.progress = 1.0
            job.completed_at = datetime.utcnow()

            model.status = TrainingStatus.COMPLETED
            model.accuracy = 0.95  # シミュレーション
            model.metrics = {
                "wer": 0.05,  # Word Error Rate
                "cer": 0.02,  # Character Error Rate
                "loss": 0.12,
            }
            model.updated_at = datetime.utcnow()

        except Exception as e:
            job.status = TrainingStatus.FAILED
            job.error_message = str(e)
            if model:
                model.status = TrainingStatus.FAILED
                model.updated_at = datetime.utcnow()

    async def get_training_job(self, job_id: str) -> Optional[TrainingJob]:
        """学習ジョブを取得"""
        return self._training_jobs.get(job_id)

    async def cancel_training(self, job_id: str) -> bool:
        """学習をキャンセル"""
        job = self._training_jobs.get(job_id)
        if job and job.status in [TrainingStatus.PENDING, TrainingStatus.PREPARING, TrainingStatus.TRAINING]:
            job.status = TrainingStatus.CANCELLED
            job.completed_at = datetime.utcnow()

            model = self._models.get(job.model_id)
            if model:
                model.status = TrainingStatus.CANCELLED
                model.updated_at = datetime.utcnow()

            return True
        return False

    async def deploy_model(self, model_id: str) -> Dict[str, Any]:
        """モデルをデプロイ"""
        model = self._models.get(model_id)
        if not model:
            raise ValueError("Model not found")

        if model.status != TrainingStatus.COMPLETED:
            raise ValueError("Model is not ready for deployment")

        # デプロイ情報を返す
        return {
            "model_id": model_id,
            "endpoint": f"/api/v1/models/{model_id}/infer",
            "status": "deployed",
            "version": model.version,
        }


class FeedbackCollector:
    """フィードバック収集・学習"""

    def __init__(self):
        self._feedback: Dict[str, FeedbackEntry] = {}
        self._vocabulary_updates: Dict[str, List[str]] = {}  # tenant_id -> words

    async def submit_correction(
        self,
        transcription_id: str,
        user_id: str,
        original_text: str,
        corrected_text: str,
        segment_start_ms: int,
        segment_end_ms: int,
    ) -> FeedbackEntry:
        """修正を提出"""
        feedback_id = str(uuid.uuid4())
        entry = FeedbackEntry(
            id=feedback_id,
            transcription_id=transcription_id,
            user_id=user_id,
            original_text=original_text,
            corrected_text=corrected_text,
            segment_start_ms=segment_start_ms,
            segment_end_ms=segment_end_ms,
            created_at=datetime.utcnow(),
        )
        self._feedback[feedback_id] = entry
        return entry

    async def get_corrections(
        self,
        tenant_id: str,
        limit: int = 100,
        unapplied_only: bool = True,
    ) -> List[FeedbackEntry]:
        """修正一覧を取得"""
        entries = list(self._feedback.values())
        if unapplied_only:
            entries = [e for e in entries if not e.applied]
        return entries[:limit]

    async def add_vocabulary(
        self,
        tenant_id: str,
        words: List[str],
    ) -> int:
        """カスタム語彙を追加"""
        if tenant_id not in self._vocabulary_updates:
            self._vocabulary_updates[tenant_id] = []

        # 重複を除いて追加
        existing = set(self._vocabulary_updates[tenant_id])
        new_words = [w for w in words if w not in existing]
        self._vocabulary_updates[tenant_id].extend(new_words)

        return len(new_words)

    async def get_vocabulary(self, tenant_id: str) -> List[str]:
        """カスタム語彙を取得"""
        return self._vocabulary_updates.get(tenant_id, [])

    async def generate_training_data(
        self,
        tenant_id: str,
        min_samples: int = 100,
    ) -> Dict[str, Any]:
        """フィードバックから学習データを生成"""
        corrections = await self.get_corrections(tenant_id, limit=1000, unapplied_only=True)
        vocabulary = await self.get_vocabulary(tenant_id)

        return {
            "corrections_count": len(corrections),
            "vocabulary_count": len(vocabulary),
            "ready_for_training": len(corrections) >= min_samples,
            "samples": [
                {
                    "original": c.original_text,
                    "corrected": c.corrected_text,
                }
                for c in corrections
            ],
            "vocabulary": vocabulary,
        }


class AutoLearningScheduler:
    """自動学習スケジューラー"""

    def __init__(
        self,
        model_manager: CustomModelManager,
        dataset_manager: DatasetManager,
        feedback_collector: FeedbackCollector,
    ):
        self.model_manager = model_manager
        self.dataset_manager = dataset_manager
        self.feedback_collector = feedback_collector
        self._schedules: Dict[str, Dict[str, Any]] = {}

    async def configure_auto_learning(
        self,
        tenant_id: str,
        model_id: str,
        min_samples: int = 100,
        trigger_interval_hours: int = 24,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """自動学習を設定"""
        schedule = {
            "tenant_id": tenant_id,
            "model_id": model_id,
            "min_samples": min_samples,
            "trigger_interval_hours": trigger_interval_hours,
            "enabled": enabled,
            "last_triggered": None,
            "next_trigger": None,
        }
        self._schedules[tenant_id] = schedule
        return schedule

    async def check_and_trigger(self, tenant_id: str) -> Optional[TrainingJob]:
        """条件を確認して学習をトリガー"""
        schedule = self._schedules.get(tenant_id)
        if not schedule or not schedule["enabled"]:
            return None

        # フィードバックデータを確認
        training_data = await self.feedback_collector.generate_training_data(
            tenant_id,
            min_samples=schedule["min_samples"],
        )

        if not training_data["ready_for_training"]:
            return None

        # データセットを作成
        dataset = await self.dataset_manager.create_dataset(
            name=f"auto_generated_{datetime.utcnow().strftime('%Y%m%d')}",
            dataset_type=DatasetType.TEXT_CORRECTION,
            tenant_id=tenant_id,
        )

        # サンプルを追加
        await self.dataset_manager.add_samples(dataset.id, training_data["samples"])

        # 学習を開始
        job = await self.model_manager.start_training(
            model_id=schedule["model_id"],
            dataset_ids=[dataset.id],
        )

        schedule["last_triggered"] = datetime.utcnow()
        return job

    async def get_schedule(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """スケジュールを取得"""
        return self._schedules.get(tenant_id)


class ModelEvaluator:
    """モデル評価"""

    async def evaluate(
        self,
        model_id: str,
        test_samples: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """モデルを評価"""
        # シミュレーション
        return {
            "wer": 0.05,  # Word Error Rate
            "cer": 0.02,  # Character Error Rate
            "accuracy": 0.95,
            "precision": 0.94,
            "recall": 0.96,
            "f1": 0.95,
        }

    async def compare_models(
        self,
        model_ids: List[str],
        test_samples: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """複数モデルを比較"""
        results = []
        for model_id in model_ids:
            metrics = await self.evaluate(model_id, test_samples)
            results.append({
                "model_id": model_id,
                "metrics": metrics,
            })

        # 精度でソート
        results.sort(key=lambda x: x["metrics"]["accuracy"], reverse=True)
        return results

    async def ab_test(
        self,
        model_a_id: str,
        model_b_id: str,
        traffic_split: float = 0.5,
    ) -> Dict[str, Any]:
        """A/Bテストを設定"""
        return {
            "test_id": str(uuid.uuid4()),
            "model_a": model_a_id,
            "model_b": model_b_id,
            "traffic_split": traffic_split,
            "status": "active",
            "started_at": datetime.utcnow().isoformat(),
        }


# グローバルインスタンス
dataset_manager = DatasetManager()
model_manager = CustomModelManager()
feedback_collector = FeedbackCollector()
auto_learning_scheduler = AutoLearningScheduler(model_manager, dataset_manager, feedback_collector)
model_evaluator = ModelEvaluator()
