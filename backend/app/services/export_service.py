import io
import json
from datetime import timedelta

from app.models.transcription import Segment, Speaker


class ExportService:
    """エクスポートサービス"""

    def __init__(self):
        pass

    def export_txt(self, segments: list[Segment], speakers: list[Speaker] | None = None) -> str:
        """プレーンテキスト形式でエクスポート"""
        speaker_map = {s.id: s.label for s in (speakers or [])}
        lines = []

        for seg in segments:
            speaker_label = speaker_map.get(seg.speaker_id, "")
            prefix = f"[{speaker_label}] " if speaker_label else ""
            lines.append(f"{prefix}{seg.text}")

        return "\n".join(lines)

    def export_srt(self, segments: list[Segment]) -> str:
        """SRT形式でエクスポート"""
        lines = []

        for i, seg in enumerate(segments, 1):
            start = self._format_srt_time(seg.start_time_ms)
            end = self._format_srt_time(seg.end_time_ms)
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")

        return "\n".join(lines)

    def export_vtt(self, segments: list[Segment]) -> str:
        """WebVTT形式でエクスポート"""
        lines = ["WEBVTT", ""]

        for seg in segments:
            start = self._format_vtt_time(seg.start_time_ms)
            end = self._format_vtt_time(seg.end_time_ms)
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")

        return "\n".join(lines)

    def export_json(
        self, segments: list[Segment], speakers: list[Speaker] | None = None
    ) -> str:
        """JSON形式でエクスポート"""
        speaker_map = {str(s.id): {"label": s.label, "color": s.color} for s in (speakers or [])}

        data = {
            "speakers": speaker_map,
            "segments": [
                {
                    "start_time_ms": seg.start_time_ms,
                    "end_time_ms": seg.end_time_ms,
                    "text": seg.text,
                    "speaker_id": str(seg.speaker_id) if seg.speaker_id else None,
                    "confidence": seg.confidence,
                }
                for seg in segments
            ],
        }

        return json.dumps(data, ensure_ascii=False, indent=2)

    def export_docx(
        self, segments: list[Segment], speakers: list[Speaker] | None = None, title: str = ""
    ) -> bytes:
        """DOCX形式でエクスポート"""
        try:
            from docx import Document
            from docx.shared import Pt, Inches
        except ImportError:
            raise RuntimeError("python-docx is not installed")

        doc = Document()

        # タイトル
        if title:
            doc.add_heading(title, 0)

        # 話者マップ
        speaker_map = {s.id: s.label for s in (speakers or [])}

        # セグメントを追加
        current_speaker = None
        current_paragraph = None

        for seg in segments:
            speaker_label = speaker_map.get(seg.speaker_id)

            if speaker_label and speaker_label != current_speaker:
                # 新しい話者
                current_speaker = speaker_label
                doc.add_paragraph()
                p = doc.add_paragraph()
                run = p.add_run(f"【{speaker_label}】")
                run.bold = True
                p.add_run(" " + seg.text)
                current_paragraph = p
            elif current_paragraph:
                # 同じ話者、続きを追加
                current_paragraph.add_run(" " + seg.text)
            else:
                # 話者なし
                doc.add_paragraph(seg.text)

        # バイトストリームに保存
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.read()

    def _format_srt_time(self, ms: int) -> str:
        """ミリ秒をSRT形式の時刻文字列に変換"""
        td = timedelta(milliseconds=ms)
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _format_vtt_time(self, ms: int) -> str:
        """ミリ秒をVTT形式の時刻文字列に変換"""
        td = timedelta(milliseconds=ms)
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def get_export_content_type(format: str) -> str:
    """エクスポート形式からContent-Typeを取得"""
    content_types = {
        "txt": "text/plain",
        "srt": "text/plain",
        "vtt": "text/vtt",
        "json": "application/json",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return content_types.get(format, "application/octet-stream")


def get_export_extension(format: str) -> str:
    """エクスポート形式から拡張子を取得"""
    return format
