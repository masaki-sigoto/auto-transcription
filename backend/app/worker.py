import os
import tempfile
import asyncio
from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Celeryアプリケーション
celery_app = Celery(
    "voicescribe",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1時間
    worker_prefetch_multiplier=1,
)

# 同期用データベースエンジン
sync_database_url = settings.database_url.replace("+asyncpg", "")
sync_engine = create_engine(sync_database_url)
SyncSession = sessionmaker(bind=sync_engine)


@celery_app.task(bind=True, max_retries=3)
def process_transcription(self, transcription_id: str):
    """
    文字起こし処理タスク

    1. 音声ファイルをダウンロード
    2. 前処理（正規化）
    3. 文字起こし実行
    4. 話者識別（オプション）
    5. LLM補正（オプション）
    6. 結果を保存
    """
    from app.models.transcription import Transcription, Segment, Speaker
    from app.services.audio_processor import AudioProcessor
    from app.services.transcription_engine import get_engine
    from app.services.speaker_diarization import get_diarization_service
    from app.services.llm_corrector import LLMCorrector
    from app.services.storage_service import StorageService

    session = SyncSession()

    try:
        # 文字起こしレコードを取得
        transcription = session.query(Transcription).filter(
            Transcription.id == transcription_id
        ).first()

        if not transcription:
            raise ValueError(f"Transcription not found: {transcription_id}")

        # ステータスを処理中に更新
        transcription.status = "processing"
        session.commit()

        # 一時ディレクトリ
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. 音声ファイルをダウンロード
            storage = StorageService()
            audio_url = transcription.audio_url

            if audio_url.startswith("s3://"):
                # S3からダウンロード
                parts = audio_url.replace("s3://", "").split("/", 1)
                bucket = parts[0]
                key = parts[1]
                local_path = os.path.join(temp_dir, "audio_original")
                storage.download_file(key, local_path)
            elif audio_url.startswith("local://"):
                # ローカルストレージからコピー
                file_key = audio_url.replace("local://", "")
                local_path = os.path.join(temp_dir, "audio_original")
                storage.download_file(file_key, local_path)
            else:
                raise ValueError(f"Unsupported audio URL: {audio_url}")

            # 2. 前処理
            processor = AudioProcessor()
            normalized_path = processor.normalize_audio(
                local_path,
                os.path.join(temp_dir, "audio_normalized.wav")
            )

            # 音声長を取得
            duration_sec = int(processor.get_duration(normalized_path))
            transcription.audio_duration_sec = duration_sec

            # 3. 文字起こし実行
            engine = get_engine(transcription.engine)
            result = asyncio.run(
                engine.transcribe(normalized_path, transcription.language)
            )

            segments_data = [
                {
                    "start_time_ms": seg.start_time_ms,
                    "end_time_ms": seg.end_time_ms,
                    "text": seg.text,
                    "confidence": seg.confidence,
                }
                for seg in result.segments
            ]

            # 4. 話者識別（オプション）
            speaker_map = {}
            if transcription.enable_diarization:
                try:
                    # 環境変数でpyannote使用を制御（HF_AUTH_TOKENが必要）
                    use_pyannote = bool(os.getenv("USE_PYANNOTE", "").lower() in ("true", "1", "yes"))
                    diarization = get_diarization_service(use_pyannote=use_pyannote)

                    # 話者数を指定するか自動検出
                    diarization_params = {}
                    if use_pyannote:
                        # pyannoteは自動で話者数を推定できる
                        diarization_params = {"min_speakers": 1, "max_speakers": 10}
                    else:
                        # 簡易版は話者数指定が必要
                        diarization_params = {"num_speakers": 2}

                    speaker_segments = asyncio.run(
                        diarization.diarize(normalized_path, **diarization_params)
                    )

                    # 話者IDを収集
                    unique_speakers = set(s.speaker_id for s in speaker_segments)
                    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]

                    for i, speaker_id in enumerate(unique_speakers):
                        speaker = Speaker(
                            transcription_id=transcription.id,
                            label=f"話者 {i + 1}",
                            color=colors[i % len(colors)],
                        )
                        session.add(speaker)
                        session.flush()
                        speaker_map[speaker_id] = str(speaker.id)

                    # 文字起こしセグメントに話者をマッピング
                    segments_data = diarization.merge_with_transcription(
                        segments_data, speaker_segments
                    )

                    # speaker_idをUUIDに変換
                    for seg in segments_data:
                        if seg.get("speaker_id") and seg["speaker_id"] in speaker_map:
                            seg["speaker_id"] = speaker_map[seg["speaker_id"]]
                        else:
                            seg["speaker_id"] = None

                except Exception as e:
                    print(f"Diarization failed: {e}")
                    # 話者識別失敗しても続行

            # 5. LLM補正（オプション）
            if transcription.enable_llm_correction and settings.anthropic_api_key:
                try:
                    from app.services.transcription_engine import TranscriptionSegment

                    corrector = LLMCorrector()
                    segments_for_correction = [
                        TranscriptionSegment(
                            start_time_ms=s["start_time_ms"],
                            end_time_ms=s["end_time_ms"],
                            text=s["text"],
                            confidence=s.get("confidence"),
                        )
                        for s in segments_data
                    ]

                    corrected = asyncio.run(
                        corrector.correct_segments(segments_for_correction)
                    )

                    # 補正結果を反映
                    for i, seg in enumerate(corrected):
                        segments_data[i]["text"] = seg.text

                except Exception as e:
                    print(f"LLM correction failed: {e}")
                    # LLM補正失敗しても続行

            # 6. セグメントを保存
            for seg_data in segments_data:
                segment = Segment(
                    transcription_id=transcription.id,
                    start_time_ms=seg_data["start_time_ms"],
                    end_time_ms=seg_data["end_time_ms"],
                    text=seg_data["text"],
                    speaker_id=seg_data.get("speaker_id"),
                    confidence=seg_data.get("confidence"),
                )
                session.add(segment)

            # 完了
            transcription.status = "completed"
            session.commit()

            return {
                "status": "completed",
                "transcription_id": transcription_id,
                "segments_count": len(segments_data),
                "duration_sec": duration_sec,
            }

    except Exception as e:
        session.rollback()

        # エラーステータスを設定
        try:
            transcription = session.query(Transcription).filter(
                Transcription.id == transcription_id
            ).first()
            if transcription:
                transcription.status = "failed"
                transcription.error_message = str(e)
                session.commit()
        except Exception:
            pass

        # リトライ
        raise self.retry(exc=e, countdown=60)

    finally:
        session.close()


@celery_app.task
def cleanup_old_audio_files():
    """
    古い音声ファイルを削除するタスク
    毎日実行
    """
    from datetime import datetime, timedelta
    from app.models.transcription import Transcription
    from app.services.storage_service import StorageService

    session = SyncSession()
    storage = StorageService()

    try:
        # 24時間以上前の完了した文字起こし
        threshold = datetime.utcnow() - timedelta(hours=24)

        transcriptions = session.query(Transcription).filter(
            Transcription.status == "completed",
            Transcription.updated_at < threshold,
        ).all()

        deleted_count = 0
        for trans in transcriptions:
            if trans.audio_url and trans.audio_url.startswith("s3://"):
                try:
                    parts = trans.audio_url.replace("s3://", "").split("/", 1)
                    key = parts[1]
                    storage.delete_file(key)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {trans.audio_url}: {e}")

        return {"deleted_count": deleted_count}

    finally:
        session.close()


# Celery Beat スケジュール
celery_app.conf.beat_schedule = {
    "cleanup-old-audio-files": {
        "task": "app.worker.cleanup_old_audio_files",
        "schedule": 86400,  # 24時間
    },
}
