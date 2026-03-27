"""音声合成・テキスト読み上げサービス"""

import os
import asyncio
import uuid
import tempfile
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime
import httpx


class TTSProvider(str, Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    AZURE = "azure"
    ELEVENLABS = "elevenlabs"
    LOCAL = "local"


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class AudioFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"
    OGG = "ogg"
    FLAC = "flac"


@dataclass
class Voice:
    id: str
    name: str
    language: str
    gender: VoiceGender
    provider: TTSProvider
    preview_url: Optional[str] = None
    description: Optional[str] = None


@dataclass
class TTSConfig:
    voice_id: str
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    format: AudioFormat = AudioFormat.MP3
    sample_rate: int = 22050


@dataclass
class TTSResult:
    audio_path: str
    duration_sec: float
    format: AudioFormat
    file_size_bytes: int
    provider: TTSProvider


class BaseTTSClient(ABC):
    """TTSクライアントの基底クラス"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
    ) -> TTSResult:
        pass

    @abstractmethod
    async def list_voices(
        self,
        language: Optional[str] = None,
    ) -> List[Voice]:
        pass


class OpenAITTSClient(BaseTTSClient):
    """OpenAI TTS クライアント"""

    VOICES = {
        "alloy": Voice(id="alloy", name="Alloy", language="en", gender=VoiceGender.NEUTRAL, provider=TTSProvider.OPENAI),
        "echo": Voice(id="echo", name="Echo", language="en", gender=VoiceGender.MALE, provider=TTSProvider.OPENAI),
        "fable": Voice(id="fable", name="Fable", language="en", gender=VoiceGender.NEUTRAL, provider=TTSProvider.OPENAI),
        "onyx": Voice(id="onyx", name="Onyx", language="en", gender=VoiceGender.MALE, provider=TTSProvider.OPENAI),
        "nova": Voice(id="nova", name="Nova", language="en", gender=VoiceGender.FEMALE, provider=TTSProvider.OPENAI),
        "shimmer": Voice(id="shimmer", name="Shimmer", language="en", gender=VoiceGender.FEMALE, provider=TTSProvider.OPENAI),
    }

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"

    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
    ) -> TTSResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": config.voice_id,
                    "response_format": config.format.value,
                    "speed": config.speed,
                },
                timeout=60,
            )
            response.raise_for_status()

            # 音声ファイルを保存
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"tts_{uuid.uuid4().hex}.{config.format.value}"
            )

            with open(output_path, "wb") as f:
                f.write(response.content)

            file_size = os.path.getsize(output_path)

            # 概算の再生時間
            duration_sec = len(text) / 15.0 / config.speed

            return TTSResult(
                audio_path=output_path,
                duration_sec=duration_sec,
                format=config.format,
                file_size_bytes=file_size,
                provider=TTSProvider.OPENAI,
            )

    async def list_voices(
        self,
        language: Optional[str] = None,
    ) -> List[Voice]:
        return list(self.VOICES.values())


class GoogleTTSClient(BaseTTSClient):
    """Google Cloud TTS クライアント"""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.base_url = "https://texttospeech.googleapis.com/v1"

    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
    ) -> TTSResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/text:synthesize?key={self.api_key}",
                json={
                    "input": {"text": text},
                    "voice": {
                        "languageCode": "ja-JP",
                        "name": config.voice_id,
                    },
                    "audioConfig": {
                        "audioEncoding": "MP3",
                        "speakingRate": config.speed,
                        "pitch": config.pitch,
                        "volumeGainDb": (config.volume - 1.0) * 10,
                    },
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            import base64
            audio_content = base64.b64decode(data["audioContent"])

            output_path = os.path.join(
                tempfile.gettempdir(),
                f"tts_{uuid.uuid4().hex}.mp3"
            )

            with open(output_path, "wb") as f:
                f.write(audio_content)

            file_size = os.path.getsize(output_path)
            duration_sec = len(text) / 15.0 / config.speed

            return TTSResult(
                audio_path=output_path,
                duration_sec=duration_sec,
                format=AudioFormat.MP3,
                file_size_bytes=file_size,
                provider=TTSProvider.GOOGLE,
            )

    async def list_voices(
        self,
        language: Optional[str] = None,
    ) -> List[Voice]:
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/voices?key={self.api_key}"
            if language:
                url += f"&languageCode={language}"

            response = await client.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            voices = []
            for voice in data.get("voices", []):
                gender = VoiceGender.NEUTRAL
                if voice.get("ssmlGender") == "MALE":
                    gender = VoiceGender.MALE
                elif voice.get("ssmlGender") == "FEMALE":
                    gender = VoiceGender.FEMALE

                voices.append(Voice(
                    id=voice["name"],
                    name=voice["name"],
                    language=voice["languageCodes"][0] if voice.get("languageCodes") else "en",
                    gender=gender,
                    provider=TTSProvider.GOOGLE,
                ))

            return voices


class ElevenLabsTTSClient(BaseTTSClient):
    """ElevenLabs TTS クライアント"""

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1"

    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
    ) -> TTSResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{config.voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
                timeout=60,
            )
            response.raise_for_status()

            output_path = os.path.join(
                tempfile.gettempdir(),
                f"tts_{uuid.uuid4().hex}.mp3"
            )

            with open(output_path, "wb") as f:
                f.write(response.content)

            file_size = os.path.getsize(output_path)
            duration_sec = len(text) / 15.0 / config.speed

            return TTSResult(
                audio_path=output_path,
                duration_sec=duration_sec,
                format=AudioFormat.MP3,
                file_size_bytes=file_size,
                provider=TTSProvider.ELEVENLABS,
            )

    async def list_voices(
        self,
        language: Optional[str] = None,
    ) -> List[Voice]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/voices",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            voices = []
            for voice in data.get("voices", []):
                labels = voice.get("labels", {})
                gender = VoiceGender.NEUTRAL
                if labels.get("gender") == "male":
                    gender = VoiceGender.MALE
                elif labels.get("gender") == "female":
                    gender = VoiceGender.FEMALE

                voices.append(Voice(
                    id=voice["voice_id"],
                    name=voice["name"],
                    language=labels.get("language", "en"),
                    gender=gender,
                    provider=TTSProvider.ELEVENLABS,
                    preview_url=voice.get("preview_url"),
                    description=voice.get("description"),
                ))

            return voices


class TTSService:
    """統合TTSサービス"""

    def __init__(self, default_provider: TTSProvider = TTSProvider.OPENAI):
        self.default_provider = default_provider
        self.clients: Dict[TTSProvider, BaseTTSClient] = {
            TTSProvider.OPENAI: OpenAITTSClient(),
            TTSProvider.GOOGLE: GoogleTTSClient(),
            TTSProvider.ELEVENLABS: ElevenLabsTTSClient(),
        }

    def get_client(self, provider: Optional[TTSProvider] = None) -> BaseTTSClient:
        provider = provider or self.default_provider
        return self.clients[provider]

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        provider: Optional[TTSProvider] = None,
        speed: float = 1.0,
        pitch: float = 1.0,
        format: AudioFormat = AudioFormat.MP3,
    ) -> TTSResult:
        """テキストを音声に変換"""
        client = self.get_client(provider)

        config = TTSConfig(
            voice_id=voice_id,
            speed=speed,
            pitch=pitch,
            format=format,
        )

        return await client.synthesize(text, config)

    async def list_voices(
        self,
        provider: Optional[TTSProvider] = None,
        language: Optional[str] = None,
    ) -> List[Voice]:
        """利用可能な音声一覧を取得"""
        if provider:
            client = self.get_client(provider)
            return await client.list_voices(language)

        # 全プロバイダーから取得
        all_voices = []
        for client in self.clients.values():
            try:
                voices = await client.list_voices(language)
                all_voices.extend(voices)
            except Exception:
                pass

        return all_voices


class TranscriptionReadbackService:
    """文字起こし読み上げサービス"""

    def __init__(self, tts_service: Optional[TTSService] = None):
        self.tts = tts_service or TTSService()

    async def generate_readback(
        self,
        segments: List[Dict[str, Any]],
        voice_mapping: Optional[Dict[str, str]] = None,
        provider: TTSProvider = TTSProvider.OPENAI,
        format: AudioFormat = AudioFormat.MP3,
    ) -> Dict[str, Any]:
        """文字起こしセグメントから音声を生成"""
        voice_mapping = voice_mapping or {}
        audio_segments = []

        for segment in segments:
            text = segment.get("text", "")
            speaker = segment.get("speaker_id") or segment.get("speaker_name") or "default"

            # 話者に対応する音声を取得
            voice_id = voice_mapping.get(speaker, "alloy")

            result = await self.tts.synthesize(
                text=text,
                voice_id=voice_id,
                provider=provider,
                format=format,
            )

            audio_segments.append({
                "start_time_ms": segment.get("start_time_ms", 0),
                "end_time_ms": segment.get("end_time_ms", 0),
                "text": text,
                "speaker": speaker,
                "audio_path": result.audio_path,
                "duration_sec": result.duration_sec,
            })

        return {
            "segments": audio_segments,
            "total_segments": len(audio_segments),
        }

    async def merge_audio_segments(
        self,
        audio_segments: List[Dict[str, Any]],
        output_format: AudioFormat = AudioFormat.MP3,
    ) -> str:
        """音声セグメントを結合"""
        if not audio_segments:
            raise ValueError("No audio segments to merge")

        output_path = os.path.join(
            tempfile.gettempdir(),
            f"merged_{uuid.uuid4().hex}.{output_format.value}"
        )

        # FFmpegで結合
        file_list_path = os.path.join(
            tempfile.gettempdir(),
            f"filelist_{uuid.uuid4().hex}.txt"
        )

        with open(file_list_path, "w") as f:
            for seg in audio_segments:
                f.write(f"file '{seg['audio_path']}'\n")

        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", file_list_path,
            "-c", "copy",
            "-y",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        os.remove(file_list_path)

        return output_path


class VoiceCloningService:
    """音声クローニングサービス（ElevenLabs）"""

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1"

    async def create_voice_clone(
        self,
        name: str,
        audio_files: List[str],
        description: Optional[str] = None,
    ) -> Voice:
        """音声サンプルからクローンを作成"""
        async with httpx.AsyncClient() as client:
            files = []
            for audio_path in audio_files:
                with open(audio_path, "rb") as f:
                    files.append(("files", (os.path.basename(audio_path), f.read(), "audio/mpeg")))

            response = await client.post(
                f"{self.base_url}/voices/add",
                headers={"xi-api-key": self.api_key},
                data={
                    "name": name,
                    "description": description or "",
                },
                files=files,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            return Voice(
                id=data["voice_id"],
                name=name,
                language="multilingual",
                gender=VoiceGender.NEUTRAL,
                provider=TTSProvider.ELEVENLABS,
                description=description,
            )

    async def delete_voice_clone(self, voice_id: str) -> bool:
        """クローン音声を削除"""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/voices/{voice_id}",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            return response.status_code == 200


class SSMLBuilder:
    """SSML構築ヘルパー"""

    def __init__(self):
        self.content = []

    def speak(self) -> "SSMLBuilder":
        return self

    def text(self, text: str) -> "SSMLBuilder":
        self.content.append(text)
        return self

    def pause(self, time_ms: int) -> "SSMLBuilder":
        self.content.append(f'<break time="{time_ms}ms"/>')
        return self

    def emphasis(self, text: str, level: str = "moderate") -> "SSMLBuilder":
        self.content.append(f'<emphasis level="{level}">{text}</emphasis>')
        return self

    def prosody(
        self,
        text: str,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        volume: Optional[str] = None,
    ) -> "SSMLBuilder":
        attrs = []
        if rate:
            attrs.append(f'rate="{rate}"')
        if pitch:
            attrs.append(f'pitch="{pitch}"')
        if volume:
            attrs.append(f'volume="{volume}"')

        attr_str = " ".join(attrs)
        self.content.append(f'<prosody {attr_str}>{text}</prosody>')
        return self

    def say_as(self, text: str, interpret_as: str) -> "SSMLBuilder":
        self.content.append(f'<say-as interpret-as="{interpret_as}">{text}</say-as>')
        return self

    def build(self) -> str:
        content = "".join(self.content)
        return f'<speak>{content}</speak>'
