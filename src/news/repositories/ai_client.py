"""AI client for generating daily news digest with provider abstraction."""

import json
from abc import ABC, abstractmethod

from aws_lambda_powertools import Logger
from repositories import AI_PROVIDER, GEMINI_API_KEY


class AIClient(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def select_top_news(self, news_items: list[dict]) -> list[int]:
        """Return indices of the top N news items selected by the model."""
        pass

    @abstractmethod
    def generate_final_digest(self, deep_news_items: list[dict], greeting: str) -> str:
        """Generate final digest text from deep-scraped articles and greeting."""
        pass


class GeminiAIClient(AIClient):
    """Google Gemini AI provider via google-genai: single-step digest generation."""

    def __init__(self, api_key: str):
        """Initialize Gemini client (google-genai)."""
        self.api_key = api_key
        self.logger = Logger()
        self._client = None

    def _get_client(self):
        """Lazy-init Gemini client to defer import at module load."""
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def select_top_news(self, news_items: list[dict]) -> list[int]:
        """Ask the model to pick the top 3 unique news indices."""
        if not news_items:
            return []

        payload = [{"index": n["index"], "title": n["title"], "summary": n["summary"]} for n in news_items]
        prompt = (
            "Analyze these IT news items. Cluster duplicates. Select exactly 3 of the most important UNIQUE topics.\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"top_indices": [1, 5, 8]}\n\n'
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            from google.genai import types

            response = self._get_client().models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            indices = data.get("top_indices", [0, 1, 2])
            result = [int(i) for i in indices if 0 <= int(i) < len(news_items)][:3]
            self.logger.info("Top news selected", extra={"indices": result, "pool_size": len(news_items)})
            return result
        except Exception:
            self.logger.error("Failed to select top news", exc_info=True)
            return list(range(min(3, len(news_items))))

    def generate_final_digest(self, deep_news_items: list[dict], greeting: str) -> str:
        """Generate Kazakh digest from full article texts."""
        if not deep_news_items:
            return "📭 Бүгін жаңалық жоқ."

        payload = [
            {"title": n["title"], "link": n["link"], "full_text": n.get("full_text", n["summary"])}
            for n in deep_news_items
        ]

        prompt = (
            "You are an expert IT journalist for a Kazakh developer community.\n"
            "I will give you the FULL text of 3 important IT news articles.\n"
            "Write a deep, engaging narrative digest in modern Kazakh (Cyrillic).\n\n"
            "FORMAT RULES:\n"
            f"1. Start exactly with: <b>{greeting}</b>\\n\\nМіне, қазіргі басты IT жаңалықтар:\\n\\n\n"
            "2. For each topic: Use 1 Emoji, a <b>Bold Title</b>, "
            "and 3-4 sentences of deep analysis based on the full text. Explain the impact on the industry.\n"
            '3. End each topic with the HTML link: <a href="URL">Толығырақ оқу</a>.\n'
            "4. Use \\n\\n between topics.\n"
            "5. NO raw URLs.\n"
            "6. Max 3500 characters total. You have plenty of space, so be detailed and engaging.\n\n"
            "Respond ONLY with a JSON object in this format:\n"
            '{"text": "your full html string here"}\n\n'
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            from google.genai import types

            response = self._get_client().models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            text = data.get("text", "Error generating digest.")
            self.logger.info("Digest generated", extra={"length": len(text)})
            return text
        except Exception:
            self.logger.error("Failed to generate digest", exc_info=True)
            return f"<b>{deep_news_items[0]['title']}</b>\n{deep_news_items[0]['link']}"


def create_ai_client() -> AIClient:
    """Factory function to create AI client based on provider."""
    provider = AI_PROVIDER.lower()
    if provider == "gemini":
        return GeminiAIClient(api_key=GEMINI_API_KEY)
    raise ValueError(f"Unsupported AI provider: {AI_PROVIDER}. Available: 'gemini'")
