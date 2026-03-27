"""AI自動学習・カスタムモデルAPIエンドポイント"""

import uuid
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.services.ai_learning_service import (
    dataset_manager,
    model_manager,
    feedback_collector,
    auto_learning_scheduler,
    model_evaluator,
    ModelType,
    TrainingStatus,
    DatasetType,
)

router = APIRouter(prefix="/ai-learning", tags=["ai-learning"])


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_tenant_id() -> str:
    return "default-tenant"


# === データセット ===

class CreateDatasetRequest(BaseModel):
    name: str
    type: DatasetType


@router.post("/datasets")
async def create_dataset(
    request: CreateDatasetRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データセットを作成"""
    dataset = await dataset_manager.create_dataset(
        name=request.name,
        dataset_type=request.type,
        tenant_id=tenant_id,
    )

    return {
        "id": dataset.id,
        "name": dataset.name,
        "type": dataset.type.value,
        "sample_count": dataset.sample_count,
        "created_at": dataset.created_at.isoformat(),
    }


@router.get("/datasets")
async def list_datasets(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データセット一覧"""
    datasets = await dataset_manager.list_datasets(tenant_id)

    return {
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "type": d.type.value,
                "sample_count": d.sample_count,
                "size_bytes": d.size_bytes,
                "created_at": d.created_at.isoformat(),
            }
            for d in datasets
        ]
    }


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データセットを取得"""
    dataset = await dataset_manager.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {
        "id": dataset.id,
        "name": dataset.name,
        "type": dataset.type.value,
        "sample_count": dataset.sample_count,
        "size_bytes": dataset.size_bytes,
        "validation_split": dataset.validation_split,
        "created_at": dataset.created_at.isoformat(),
        "metadata": dataset.metadata,
    }


class AddSamplesRequest(BaseModel):
    samples: List[dict]


@router.post("/datasets/{dataset_id}/samples")
async def add_samples(
    dataset_id: str,
    request: AddSamplesRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """サンプルを追加"""
    try:
        count = await dataset_manager.add_samples(dataset_id, request.samples)
        return {"added": count, "dataset_id": dataset_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """データセットを削除"""
    success = await dataset_manager.delete_dataset(dataset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {"status": "deleted", "dataset_id": dataset_id}


# === カスタムモデル ===

class CreateModelRequest(BaseModel):
    name: str
    type: ModelType
    base_model: str = "whisper-large-v3"
    config: Optional[dict] = None


@router.post("/models")
async def create_model(
    request: CreateModelRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カスタムモデルを作成"""
    model = await model_manager.create_model(
        name=request.name,
        model_type=request.type,
        tenant_id=tenant_id,
        base_model=request.base_model,
        config=request.config,
    )

    return {
        "id": model.id,
        "name": model.name,
        "type": model.type.value,
        "base_model": model.base_model,
        "version": model.version,
        "status": model.status.value,
        "created_at": model.created_at.isoformat(),
    }


@router.get("/models")
async def list_models(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """モデル一覧"""
    models = await model_manager.list_models(tenant_id)

    return {
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "type": m.type.value,
                "base_model": m.base_model,
                "version": m.version,
                "status": m.status.value,
                "accuracy": m.accuracy,
                "created_at": m.created_at.isoformat(),
            }
            for m in models
        ]
    }


@router.get("/models/{model_id}")
async def get_model(
    model_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """モデルを取得"""
    model = await model_manager.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return {
        "id": model.id,
        "name": model.name,
        "type": model.type.value,
        "base_model": model.base_model,
        "version": model.version,
        "status": model.status.value,
        "accuracy": model.accuracy,
        "metrics": model.metrics,
        "config": model.config,
        "created_at": model.created_at.isoformat(),
        "updated_at": model.updated_at.isoformat(),
    }


# === 学習 ===

class StartTrainingRequest(BaseModel):
    dataset_ids: List[str]
    hyperparameters: Optional[dict] = None


@router.post("/models/{model_id}/train")
async def start_training(
    model_id: str,
    request: StartTrainingRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """学習を開始"""
    try:
        job = await model_manager.start_training(
            model_id=model_id,
            dataset_ids=request.dataset_ids,
            hyperparameters=request.hyperparameters,
        )

        return {
            "job_id": job.id,
            "model_id": job.model_id,
            "status": job.status.value,
            "started_at": job.started_at.isoformat() if job.started_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/training-jobs/{job_id}")
async def get_training_job(
    job_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """学習ジョブを取得"""
    job = await model_manager.get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    return {
        "id": job.id,
        "model_id": job.model_id,
        "status": job.status.value,
        "progress": job.progress,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
        "logs": job.logs[-20:],  # 最新20件
        "hyperparameters": job.hyperparameters,
    }


@router.post("/training-jobs/{job_id}/cancel")
async def cancel_training(
    job_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """学習をキャンセル"""
    success = await model_manager.cancel_training(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel training job")

    return {"status": "cancelled", "job_id": job_id}


@router.post("/models/{model_id}/deploy")
async def deploy_model(
    model_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """モデルをデプロイ"""
    try:
        result = await model_manager.deploy_model(model_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === フィードバック ===

class SubmitCorrectionRequest(BaseModel):
    transcription_id: str
    original_text: str
    corrected_text: str
    segment_start_ms: int
    segment_end_ms: int


@router.post("/feedback/corrections")
async def submit_correction(
    request: SubmitCorrectionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """修正を提出"""
    entry = await feedback_collector.submit_correction(
        transcription_id=request.transcription_id,
        user_id=str(user_id),
        original_text=request.original_text,
        corrected_text=request.corrected_text,
        segment_start_ms=request.segment_start_ms,
        segment_end_ms=request.segment_end_ms,
    )

    return {
        "id": entry.id,
        "transcription_id": entry.transcription_id,
        "created_at": entry.created_at.isoformat(),
    }


@router.get("/feedback/corrections")
async def list_corrections(
    limit: int = Query(100, le=1000),
    unapplied_only: bool = True,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """修正一覧"""
    corrections = await feedback_collector.get_corrections(
        tenant_id=tenant_id,
        limit=limit,
        unapplied_only=unapplied_only,
    )

    return {
        "corrections": [
            {
                "id": c.id,
                "transcription_id": c.transcription_id,
                "original_text": c.original_text,
                "corrected_text": c.corrected_text,
                "applied": c.applied,
                "created_at": c.created_at.isoformat(),
            }
            for c in corrections
        ],
        "total": len(corrections),
    }


class AddVocabularyRequest(BaseModel):
    words: List[str]


@router.post("/feedback/vocabulary")
async def add_vocabulary(
    request: AddVocabularyRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カスタム語彙を追加"""
    count = await feedback_collector.add_vocabulary(tenant_id, request.words)
    return {"added": count, "words": request.words}


@router.get("/feedback/vocabulary")
async def get_vocabulary(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """カスタム語彙を取得"""
    vocabulary = await feedback_collector.get_vocabulary(tenant_id)
    return {"vocabulary": vocabulary, "count": len(vocabulary)}


# === 自動学習 ===

class ConfigureAutoLearningRequest(BaseModel):
    model_id: str
    min_samples: int = 100
    trigger_interval_hours: int = 24
    enabled: bool = True


@router.post("/auto-learning/configure")
async def configure_auto_learning(
    request: ConfigureAutoLearningRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """自動学習を設定"""
    schedule = await auto_learning_scheduler.configure_auto_learning(
        tenant_id=tenant_id,
        model_id=request.model_id,
        min_samples=request.min_samples,
        trigger_interval_hours=request.trigger_interval_hours,
        enabled=request.enabled,
    )

    return schedule


@router.get("/auto-learning/status")
async def get_auto_learning_status(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """自動学習ステータス"""
    schedule = await auto_learning_scheduler.get_schedule(tenant_id)
    if not schedule:
        return {"configured": False}

    training_data = await feedback_collector.generate_training_data(
        tenant_id,
        min_samples=schedule["min_samples"],
    )

    return {
        "configured": True,
        "enabled": schedule["enabled"],
        "model_id": schedule["model_id"],
        "min_samples": schedule["min_samples"],
        "current_samples": training_data["corrections_count"],
        "ready_for_training": training_data["ready_for_training"],
        "last_triggered": schedule.get("last_triggered"),
    }


@router.post("/auto-learning/trigger")
async def trigger_auto_learning(
    tenant_id: str = Depends(get_current_tenant_id),
):
    """自動学習を手動トリガー"""
    job = await auto_learning_scheduler.check_and_trigger(tenant_id)
    if not job:
        raise HTTPException(status_code=400, detail="Not ready for training")

    return {
        "job_id": job.id,
        "model_id": job.model_id,
        "status": job.status.value,
    }


# === 評価 ===

class EvaluateModelRequest(BaseModel):
    test_samples: List[dict]


@router.post("/models/{model_id}/evaluate")
async def evaluate_model(
    model_id: str,
    request: EvaluateModelRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """モデルを評価"""
    metrics = await model_evaluator.evaluate(model_id, request.test_samples)
    return {"model_id": model_id, "metrics": metrics}


class CompareModelsRequest(BaseModel):
    model_ids: List[str]
    test_samples: List[dict]


@router.post("/models/compare")
async def compare_models(
    request: CompareModelsRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """モデルを比較"""
    results = await model_evaluator.compare_models(
        request.model_ids,
        request.test_samples,
    )
    return {"comparisons": results}


class ABTestRequest(BaseModel):
    model_a_id: str
    model_b_id: str
    traffic_split: float = 0.5


@router.post("/models/ab-test")
async def create_ab_test(
    request: ABTestRequest,
    tenant_id: str = Depends(get_current_tenant_id),
):
    """A/Bテストを作成"""
    result = await model_evaluator.ab_test(
        request.model_a_id,
        request.model_b_id,
        request.traffic_split,
    )
    return result


# === プリセットモデル ===

@router.get("/base-models")
async def list_base_models():
    """利用可能なベースモデル一覧"""
    return {
        "base_models": [
            {
                "id": "whisper-large-v3",
                "name": "Whisper Large V3",
                "provider": "OpenAI",
                "languages": ["ja", "en", "zh", "ko", "multi"],
                "description": "高精度な多言語音声認識モデル",
                "recommended": True,
            },
            {
                "id": "whisper-medium",
                "name": "Whisper Medium",
                "provider": "OpenAI",
                "languages": ["ja", "en", "zh", "ko", "multi"],
                "description": "バランスの取れた音声認識モデル",
                "recommended": False,
            },
            {
                "id": "faster-whisper-large-v3",
                "name": "Faster Whisper Large V3",
                "provider": "Community",
                "languages": ["ja", "en", "zh", "ko", "multi"],
                "description": "高速化されたWhisperモデル",
                "recommended": False,
            },
            {
                "id": "reazonspeech-v2",
                "name": "ReazonSpeech V2",
                "provider": "Reazon Holdings",
                "languages": ["ja"],
                "description": "日本語特化の高精度モデル",
                "recommended": True,
            },
        ]
    }
