"""AI client for generating daily news digest with provider abstraction."""

import json
from abc import ABC, abstractmethod

from aws_lambda_powertools import Logger
from google import genai
from google.genai import types
from repositories import AI_PROVIDER, GEMINI_API_KEY, LLM_MODEL


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

    @abstractmethod
    def generate_digests_per_article(self, deep_news_items: list[dict], chat_lang: str) -> list[str]:
        """Generate one digest text per article (no greeting; for pairing with each image)."""
        pass


class GeminiAIClient(AIClient):
    """Google Gemini AI provider via google-genai: single-step digest generation."""

    def __init__(self, api_key: str):
        """Initialize Gemini client (google-genai)."""
        self.api_key = api_key
        self.logger = Logger()
        self._client = genai.Client(api_key=self.api_key)

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
            response = self._client.models.generate_content(
                model=LLM_MODEL,
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
            response = self._client.models.generate_content(
                model=LLM_MODEL,
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

    def generate_digests_per_article(self, deep_news_items: list[dict], chat_lang: str) -> list[str]:
        """Generate one Kazakh digest block per article for pairing with images."""
        if not deep_news_items:
            return []

        payload = [
            {"title": n["title"], "link": n["link"], "full_text": n.get("full_text", n["summary"])}
            for n in deep_news_items
        ]
        community_name = "Chinese developer community" if chat_lang == "zh" else "Kazakh developer community"
        language = "Chinese (Simplified)" if chat_lang == "zh" else "Kazakh (Cyrillic)"

        prompt = (
            f"You are an expert IT journalist for a {community_name}.\n"
            "I will give you the FULL text of several IT news articles.\n"
            f"For EACH article, write ONE digest block in modern {language}.\n\n"
            "FORMAT RULES per block:\n"
            "1. One Emoji, then <b>Bold Title</b>, then add two new lines after the title."
            "then 3-4 sentences of deep analysis based on the full text.\n"
            '2. End with the HTML link: <a href="URL">Толығырақ оқу</a>.\n'
            "3. NO raw URLs. Use \\n\\n between blocks.\n"
            "4. Each block max ~800 characters. Return exactly one block per article.\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"digests": ["block1 html string", "block2 ...", "block3 ..."]}\n\n'
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            response = self._client.models.generate_content(
                model=LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            digests = data.get("digests", [])
            if len(digests) != len(deep_news_items):
                self.logger.warning(
                    "Digest count mismatch, padding or trimming",
                    extra={"got": len(digests), "expected": len(deep_news_items)},
                )
            result = [
                (
                    digests[i]
                    if i < len(digests)
                    else f"<b>{deep_news_items[i]['title']}</b>\n{deep_news_items[i]['link']}"
                )
                for i in range(len(deep_news_items))
            ]
            self.logger.info("Per-article digests generated", extra={"count": len(result)})
            return result
        except Exception:
            self.logger.error("Failed to generate per-article digests", exc_info=True)
            return [f"<b>{n['title']}</b>\n{n['link']}" for n in deep_news_items]


def create_ai_client() -> AIClient:
    """Factory function to create AI client based on provider."""
    provider = AI_PROVIDER.lower()
    if provider == "gemini":
        return GeminiAIClient(api_key=GEMINI_API_KEY)
    raise ValueError(f"Unsupported AI provider: {AI_PROVIDER}. Available: 'gemini'")
