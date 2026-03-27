"""LLM統合サービス - 複数のAIプロバイダーをサポート"""

import os
import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime
import httpx


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"


class TaskType(str, Enum):
    SUMMARY = "summary"
    MEETING_MINUTES = "meeting_minutes"
    ACTION_ITEMS = "action_items"
    SENTIMENT = "sentiment"
    TRANSLATION = "translation"
    QA = "qa"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60


@dataclass
class LLMMessage:
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: Dict[str, int]
    finish_reason: str
    latency_ms: int


class BaseLLMClient(ABC):
    """LLMクライアントの基底クラス"""

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI APIクライアント"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = config.base_url or "https://api.openai.com/v1"

    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> LLMResponse:
        start_time = datetime.now()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": kwargs.get("model", self.config.model),
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            provider=LLMProvider.OPENAI.value,
            usage=data.get("usage", {}),
            finish_reason=data["choices"][0]["finish_reason"],
            latency_ms=latency_ms,
        )

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": kwargs.get("model", self.config.model),
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "stream": True,
                },
                timeout=self.config.timeout,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if chunk["choices"][0]["delta"].get("content"):
                                yield chunk["choices"][0]["delta"]["content"]
                        except json.JSONDecodeError:
                            continue


class AnthropicClient(BaseLLMClient):
    """Anthropic APIクライアント"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = config.base_url or "https://api.anthropic.com/v1"

    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> LLMResponse:
        start_time = datetime.now()

        # システムメッセージを分離
        system_content = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": kwargs.get("model", self.config.model),
                    "messages": user_messages,
                    "system": system_content,
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            provider=LLMProvider.ANTHROPIC.value,
            usage={
                "input_tokens": data["usage"]["input_tokens"],
                "output_tokens": data["usage"]["output_tokens"],
            },
            finish_reason=data["stop_reason"],
            latency_ms=latency_ms,
        )

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        system_content = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_content = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": kwargs.get("model", self.config.model),
                    "messages": user_messages,
                    "system": system_content,
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "stream": True,
                },
                timeout=self.config.timeout,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data["type"] == "content_block_delta":
                                yield data["delta"]["text"]
                        except json.JSONDecodeError:
                            continue


class GoogleClient(BaseLLMClient):
    """Google Gemini APIクライアント"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("GOOGLE_API_KEY")
        self.base_url = config.base_url or "https://generativelanguage.googleapis.com/v1beta"

    async def chat(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> LLMResponse:
        start_time = datetime.now()

        # メッセージ形式を変換
        contents = []
        for m in messages:
            role = "user" if m.role in ["user", "system"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": m.content}],
            })

        model = kwargs.get("model", self.config.model)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/models/{model}:generateContent?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "generationConfig": {
                        "temperature": kwargs.get("temperature", self.config.temperature),
                        "maxOutputTokens": kwargs.get("max_tokens", self.config.max_tokens),
                    },
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return LLMResponse(
            content=data["candidates"][0]["content"]["parts"][0]["text"],
            model=model,
            provider=LLMProvider.GOOGLE.value,
            usage=data.get("usageMetadata", {}),
            finish_reason=data["candidates"][0].get("finishReason", "STOP"),
            latency_ms=latency_ms,
        )

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        # Geminiのストリーミング実装
        contents = []
        for m in messages:
            role = "user" if m.role in ["user", "system"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": m.content}],
            })

        model = kwargs.get("model", self.config.model)

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/models/{model}:streamGenerateContent?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "generationConfig": {
                        "temperature": kwargs.get("temperature", self.config.temperature),
                        "maxOutputTokens": kwargs.get("max_tokens", self.config.max_tokens),
                    },
                },
                timeout=self.config.timeout,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "candidates" in data:
                                text = data["candidates"][0]["content"]["parts"][0]["text"]
                                yield text
                        except (json.JSONDecodeError, KeyError):
                            continue


class LLMService:
    """統合LLMサービス"""

    def __init__(self, default_provider: LLMProvider = LLMProvider.OPENAI):
        self.default_provider = default_provider
        self.clients: Dict[LLMProvider, BaseLLMClient] = {}
        self._initialize_default_clients()

    def _initialize_default_clients(self):
        """デフォルトクライアントを初期化"""
        # OpenAI
        openai_config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
        )
        self.clients[LLMProvider.OPENAI] = OpenAIClient(openai_config)

        # Anthropic
        anthropic_config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
        )
        self.clients[LLMProvider.ANTHROPIC] = AnthropicClient(anthropic_config)

        # Google
        google_config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            model="gemini-1.5-pro",
        )
        self.clients[LLMProvider.GOOGLE] = GoogleClient(google_config)

    def get_client(self, provider: Optional[LLMProvider] = None) -> BaseLLMClient:
        """クライアントを取得"""
        provider = provider or self.default_provider
        return self.clients[provider]

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
        **kwargs,
    ) -> LLMResponse:
        """テキストを生成"""
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))

        client = self.get_client(provider)
        return await client.chat(messages, **kwargs)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """ストリーミングでテキストを生成"""
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))

        client = self.get_client(provider)
        async for chunk in client.chat_stream(messages, **kwargs):
            yield chunk


class TranscriptionAIService:
    """文字起こし専用AIサービス"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    async def generate_summary(
        self,
        text: str,
        style: str = "concise",
        language: str = "ja",
        provider: Optional[LLMProvider] = None,
    ) -> str:
        """要約を生成"""
        style_prompts = {
            "concise": "簡潔に3-5文で要約してください。",
            "detailed": "詳細な要約を段落形式で作成してください。",
            "bullet": "箇条書きで主要なポイントを挙げてください。",
            "executive": "経営層向けの要約を作成してください。",
        }

        system_prompt = f"""あなたは文字起こしテキストの要約を行う専門家です。
言語: {language}
スタイル: {style_prompts.get(style, style_prompts['concise'])}"""

        prompt = f"以下の文字起こしテキストを要約してください:\n\n{text}"

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )
        return response.content

    async def generate_meeting_minutes(
        self,
        text: str,
        template: str = "standard",
        language: str = "ja",
        provider: Optional[LLMProvider] = None,
    ) -> Dict[str, Any]:
        """議事録を生成"""
        system_prompt = f"""あなたは議事録作成の専門家です。
言語: {language}

以下のJSON形式で議事録を作成してください:
{{
    "title": "会議タイトル",
    "date": "推定日時",
    "participants": ["参加者リスト"],
    "agenda": ["議題リスト"],
    "discussion": [
        {{"topic": "トピック", "content": "内容", "speaker": "発言者"}}
    ],
    "decisions": ["決定事項リスト"],
    "action_items": [
        {{"task": "タスク", "assignee": "担当者", "due_date": "期限"}}
    ],
    "next_steps": ["次のステップ"]
}}"""

        prompt = f"以下の文字起こしから議事録を作成してください:\n\n{text}"

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )

        try:
            # JSONを抽出
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_content": response.content}

    async def extract_action_items(
        self,
        text: str,
        language: str = "ja",
        provider: Optional[LLMProvider] = None,
    ) -> List[Dict[str, str]]:
        """アクションアイテムを抽出"""
        system_prompt = f"""あなたはアクションアイテム抽出の専門家です。
言語: {language}

以下のJSON配列形式でアクションアイテムを抽出してください:
[
    {{
        "task": "タスク内容",
        "assignee": "担当者（推定）",
        "priority": "high/medium/low",
        "due_date": "期限（推定）",
        "context": "関連する文脈"
    }}
]"""

        prompt = f"以下の文字起こしからアクションアイテムを抽出してください:\n\n{text}"

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except json.JSONDecodeError:
            return []

    async def analyze_sentiment(
        self,
        text: str,
        language: str = "ja",
        provider: Optional[LLMProvider] = None,
    ) -> Dict[str, Any]:
        """感情分析を実行"""
        system_prompt = f"""あなたは感情分析の専門家です。
言語: {language}

以下のJSON形式で分析結果を返してください:
{{
    "overall_sentiment": "positive/neutral/negative",
    "sentiment_score": 0.0から1.0,
    "emotions": {{
        "joy": 0.0から1.0,
        "anger": 0.0から1.0,
        "sadness": 0.0から1.0,
        "fear": 0.0から1.0,
        "surprise": 0.0から1.0
    }},
    "tone": "formal/casual/professional/etc",
    "key_phrases": ["キーフレーズリスト"],
    "speaker_sentiments": [
        {{"speaker": "話者", "sentiment": "positive/neutral/negative"}}
    ]
}}"""

        prompt = f"以下の文字起こしの感情分析を行ってください:\n\n{text}"

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_content": response.content}

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
    ) -> str:
        """翻訳を実行"""
        system_prompt = f"""あなたはプロの翻訳者です。
ターゲット言語: {target_language}
ソース言語: {source_language or '自動検出'}

自然で流暢な翻訳を心がけてください。文化的なニュアンスも考慮してください。"""

        prompt = f"以下のテキストを翻訳してください:\n\n{text}"

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )
        return response.content

    async def answer_question(
        self,
        question: str,
        context: str,
        language: str = "ja",
        provider: Optional[LLMProvider] = None,
    ) -> str:
        """質問に回答"""
        system_prompt = f"""あなたは文字起こしテキストに基づいて質問に回答する専門家です。
言語: {language}

コンテキストに基づいて正確に回答してください。情報がない場合は「文字起こしにその情報はありません」と回答してください。"""

        prompt = f"""コンテキスト:
{context}

質問: {question}"""

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )
        return response.content

    async def custom_analysis(
        self,
        text: str,
        instruction: str,
        output_format: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
    ) -> str:
        """カスタム分析を実行"""
        system_prompt = f"""あなたは文字起こしテキストの分析専門家です。

ユーザーの指示に従って分析を行ってください。
{f'出力形式: {output_format}' if output_format else ''}"""

        prompt = f"""指示: {instruction}

テキスト:
{text}"""

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            provider=provider,
        )
        return response.content
