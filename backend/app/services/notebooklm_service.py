"""NotebookLM連携サービス

Google NotebookLMとの連携機能を提供:
- 文字起こしデータのエクスポート（NotebookLM対応形式）
- PDFやドキュメント形式での出力
- 音声ポッドキャスト用のスクリプト生成
"""

import os
import uuid
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ExportFormat(str, Enum):
    """エクスポート形式"""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    JSON = "json"
    GOOGLE_DOCS = "google_docs"


@dataclass
class NotebookSource:
    """NotebookLMソース"""
    id: str
    title: str
    content: str
    source_type: str  # transcription, summary, minutes
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PodcastScript:
    """ポッドキャストスクリプト"""
    title: str
    hosts: List[str]
    segments: List[Dict[str, Any]]
    duration_estimate_min: int
    intro: str
    outro: str


class NotebookLMExporter:
    """NotebookLM用エクスポーター"""

    def __init__(self):
        self.supported_formats = list(ExportFormat)

    def format_for_notebooklm(
        self,
        transcription_data: Dict[str, Any],
        include_timestamps: bool = True,
        include_speakers: bool = True,
    ) -> str:
        """NotebookLMに最適化された形式でフォーマット"""
        output_lines = []

        # タイトルとメタデータ
        title = transcription_data.get("title", "文字起こし")
        output_lines.append(f"# {title}")
        output_lines.append("")

        # メタデータセクション
        output_lines.append("## 概要")
        if transcription_data.get("created_at"):
            output_lines.append(f"- 作成日: {transcription_data['created_at']}")
        if transcription_data.get("audio_duration_sec"):
            duration_min = transcription_data["audio_duration_sec"] // 60
            output_lines.append(f"- 音声時間: {duration_min}分")
        if transcription_data.get("language"):
            output_lines.append(f"- 言語: {transcription_data['language']}")
        output_lines.append("")

        # 話者情報
        speakers = transcription_data.get("speakers", [])
        if speakers and include_speakers:
            output_lines.append("## 話者")
            for speaker in speakers:
                name = speaker.get("name") or speaker.get("label", "不明")
                output_lines.append(f"- {name}")
            output_lines.append("")

        # 要約があれば追加
        if transcription_data.get("summary"):
            output_lines.append("## 要約")
            output_lines.append(transcription_data["summary"])
            output_lines.append("")

        # 本文（セグメント）
        output_lines.append("## 内容")
        output_lines.append("")

        segments = transcription_data.get("segments", [])
        speaker_map = {s.get("id"): s.get("name") or s.get("label") for s in speakers}

        for segment in segments:
            line_parts = []

            # タイムスタンプ
            if include_timestamps:
                start_ms = segment.get("start_time_ms", 0)
                timestamp = self._format_timestamp(start_ms)
                line_parts.append(f"[{timestamp}]")

            # 話者
            if include_speakers:
                speaker_id = segment.get("speaker_id")
                speaker_name = speaker_map.get(speaker_id, "")
                if speaker_name:
                    line_parts.append(f"**{speaker_name}:**")

            # テキスト
            text = segment.get("text", "")
            line_parts.append(text)

            output_lines.append(" ".join(line_parts))
            output_lines.append("")

        return "\n".join(output_lines)

    def _format_timestamp(self, ms: int) -> str:
        """ミリ秒をMM:SS形式に変換"""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def export_as_source(
        self,
        transcription_data: Dict[str, Any],
        source_type: str = "transcription",
    ) -> NotebookSource:
        """NotebookLMソースとしてエクスポート"""
        content = self.format_for_notebooklm(transcription_data)

        return NotebookSource(
            id=str(uuid.uuid4()),
            title=transcription_data.get("title", "文字起こし"),
            content=content,
            source_type=source_type,
            metadata={
                "original_id": transcription_data.get("id"),
                "duration_sec": transcription_data.get("audio_duration_sec"),
                "language": transcription_data.get("language"),
                "speaker_count": len(transcription_data.get("speakers", [])),
                "segment_count": len(transcription_data.get("segments", [])),
            },
        )

    def generate_study_guide(
        self,
        transcription_data: Dict[str, Any],
    ) -> str:
        """学習ガイドを生成（NotebookLMの機能を模倣）"""
        title = transcription_data.get("title", "文字起こし")
        segments = transcription_data.get("segments", [])

        full_text = " ".join(s.get("text", "") for s in segments)

        guide = f"""# {title} - 学習ガイド

## 主要トピック
このドキュメントには以下のトピックが含まれています:
- [AIによる分析が必要]

## キーポイント
- [AIによる分析が必要]

## 質問例
1. このコンテンツの主なテーマは何ですか？
2. 重要な決定事項は何でしたか？
3. 次のアクションアイテムは何ですか？

## 用語集
- [AIによる分析が必要]

---
*このガイドは自動生成されました。NotebookLMでより詳細な分析が可能です。*
"""
        return guide


class PodcastScriptGenerator:
    """ポッドキャストスクリプト生成（Audio Overview風）"""

    def __init__(self):
        self.default_hosts = ["ホストA", "ホストB"]

    def generate_script(
        self,
        transcription_data: Dict[str, Any],
        style: str = "conversational",  # conversational, formal, casual
        target_duration_min: int = 10,
    ) -> PodcastScript:
        """文字起こしからポッドキャストスクリプトを生成"""
        title = transcription_data.get("title", "文字起こし")
        segments = transcription_data.get("segments", [])
        summary = transcription_data.get("summary", "")

        # イントロ
        intro = self._generate_intro(title, style)

        # メインセグメント
        main_segments = self._generate_main_segments(segments, summary, style)

        # アウトロ
        outro = self._generate_outro(title, style)

        return PodcastScript(
            title=f"{title} - ポッドキャスト",
            hosts=self.default_hosts,
            segments=main_segments,
            duration_estimate_min=target_duration_min,
            intro=intro,
            outro=outro,
        )

    def _generate_intro(self, title: str, style: str) -> str:
        """イントロを生成"""
        if style == "conversational":
            return f"""ホストA: みなさん、こんにちは！今日は「{title}」についてお話ししていきます。
ホストB: 面白い内容になりそうですね。さっそく見ていきましょう！"""
        elif style == "formal":
            return f"""ホストA: 本日のエピソードでは「{title}」について詳しく解説いたします。
ホストB: 重要なポイントを順番にご紹介していきます。"""
        else:
            return f"""ホストA: やあ！今日は{title}の話だね。
ホストB: うん、早速始めよう！"""

    def _generate_main_segments(
        self,
        segments: List[Dict[str, Any]],
        summary: str,
        style: str,
    ) -> List[Dict[str, Any]]:
        """メインセグメントを生成"""
        main_segments = []

        # 要約がある場合
        if summary:
            main_segments.append({
                "type": "overview",
                "host": "ホストA",
                "content": f"まず、全体の概要からお話しします。{summary}",
            })
            main_segments.append({
                "type": "reaction",
                "host": "ホストB",
                "content": "なるほど、興味深いですね。もう少し詳しく見ていきましょう。",
            })

        # セグメントからハイライトを抽出
        # 実際の実装ではAIによる分析が必要
        if segments:
            sample_text = segments[0].get("text", "")[:100]
            main_segments.append({
                "type": "discussion",
                "host": "ホストA",
                "content": f"最初のポイントとして、こういう話がありました。「{sample_text}...」",
            })
            main_segments.append({
                "type": "analysis",
                "host": "ホストB",
                "content": "これは重要なポイントですね。実際の場面を想像すると...",
            })

        return main_segments

    def _generate_outro(self, title: str, style: str) -> str:
        """アウトロを生成"""
        if style == "conversational":
            return f"""ホストA: 今日は「{title}」についてお話ししました。いかがでしたか？
ホストB: たくさんの気づきがありましたね。また次回お会いしましょう！
ホストA: ありがとうございました！"""
        elif style == "formal":
            return f"""ホストA: 以上、「{title}」についてお伝えしました。
ホストB: ご視聴ありがとうございました。"""
        else:
            return f"""ホストA: じゃあ、今日はこの辺で！
ホストB: またね！"""

    def to_script_text(self, script: PodcastScript) -> str:
        """スクリプトをテキスト形式に変換"""
        lines = [
            f"# {script.title}",
            f"想定時間: 約{script.duration_estimate_min}分",
            "",
            "## イントロ",
            script.intro,
            "",
            "## メインパート",
        ]

        for segment in script.segments:
            lines.append(f"{segment['host']}: {segment['content']}")
            lines.append("")

        lines.extend([
            "## アウトロ",
            script.outro,
        ])

        return "\n".join(lines)


class NotebookLMService:
    """NotebookLM統合サービス"""

    def __init__(self):
        self.exporter = NotebookLMExporter()
        self.podcast_generator = PodcastScriptGenerator()

    async def export_for_notebooklm(
        self,
        transcription_data: Dict[str, Any],
        format: ExportFormat = ExportFormat.MARKDOWN,
        include_timestamps: bool = True,
        include_speakers: bool = True,
    ) -> Dict[str, Any]:
        """NotebookLM用にエクスポート"""
        if format == ExportFormat.MARKDOWN:
            content = self.exporter.format_for_notebooklm(
                transcription_data,
                include_timestamps,
                include_speakers,
            )
            return {
                "format": "markdown",
                "content": content,
                "filename": f"{transcription_data.get('title', 'transcription')}.md",
            }

        elif format == ExportFormat.TXT:
            content = self.exporter.format_for_notebooklm(
                transcription_data,
                include_timestamps,
                include_speakers,
            )
            # Markdownタグを除去
            import re
            content = re.sub(r'[#*]', '', content)
            return {
                "format": "txt",
                "content": content,
                "filename": f"{transcription_data.get('title', 'transcription')}.txt",
            }

        elif format == ExportFormat.JSON:
            source = self.exporter.export_as_source(transcription_data)
            return {
                "format": "json",
                "content": json.dumps({
                    "id": source.id,
                    "title": source.title,
                    "content": source.content,
                    "source_type": source.source_type,
                    "metadata": source.metadata,
                    "created_at": source.created_at.isoformat(),
                }, ensure_ascii=False, indent=2),
                "filename": f"{transcription_data.get('title', 'transcription')}.json",
            }

        else:
            raise ValueError(f"Unsupported format: {format}")

    async def generate_podcast_script(
        self,
        transcription_data: Dict[str, Any],
        style: str = "conversational",
        target_duration_min: int = 10,
    ) -> Dict[str, Any]:
        """ポッドキャストスクリプトを生成"""
        script = self.podcast_generator.generate_script(
            transcription_data,
            style=style,
            target_duration_min=target_duration_min,
        )

        script_text = self.podcast_generator.to_script_text(script)

        return {
            "title": script.title,
            "hosts": script.hosts,
            "duration_estimate_min": script.duration_estimate_min,
            "script": script_text,
            "segments": script.segments,
        }

    async def generate_study_guide(
        self,
        transcription_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """学習ガイドを生成"""
        guide = self.exporter.generate_study_guide(transcription_data)

        return {
            "title": f"{transcription_data.get('title', '文字起こし')} - 学習ガイド",
            "content": guide,
        }

    async def prepare_audio_overview_sources(
        self,
        transcription_ids: List[str],
        transcription_service,
    ) -> List[NotebookSource]:
        """複数の文字起こしをAudio Overview用に準備"""
        sources = []

        for trans_id in transcription_ids:
            # 実際の実装ではDBから取得
            # transcription = await transcription_service.get_by_id(trans_id)
            # source = self.exporter.export_as_source(transcription)
            # sources.append(source)
            pass

        return sources
