"""AI client for generating news summaries with provider abstraction."""

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from aws_lambda_powertools import Logger
from groq import Groq
from repositories import AI_PROVIDER, GROQ_API_KEY


class AIClient(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def evaluate_impact(self, news_batch: list[dict]) -> list[dict]:
        """Rate global market impact of news (1-10 scale)."""
        pass

    @abstractmethod
    def generate_item_summaries(self, news_items: list[dict]) -> list[str]:
        """Generate one formatted Telegram message per news item."""
        pass

    def _get_no_news_message(self, language: str) -> str:
        """Get 'no news' fallback message."""
        messages = {"kk": "📭 Бүгін жаңалық жоқ.", "ru": "📭 Сегодня новостей нет.", "en": "📭 No news today."}
        return messages.get(language, messages["en"])


class GroqAIClient(AIClient):
    """Groq AI provider implementation with chunking and resilient parsing."""

    def __init__(self, api_key: str):
        """Initialize Groq client."""
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.client = Groq(api_key=self.api_key)
        self.logger = Logger()
        self._max_retries = 3

    def _call_groq_with_retry(self, **kwargs: Any) -> Any:
        """
        Call Groq chat completions API with exponential backoff retry.

        Retries only on transient errors (rate limits, connection issues, timeouts).
        Fails fast on permanent errors (auth failures, invalid model, etc.).
        """
        import groq as groq_lib

        _retryable = (
            groq_lib.RateLimitError,
            groq_lib.APIConnectionError,
            groq_lib.APITimeoutError,
        )
        for attempt in range(self._max_retries):
            try:
                return self.client.chat.completions.create(**kwargs)
            except _retryable as e:
                self.logger.warning(f"Groq API attempt {attempt + 1}/{self._max_retries} failed (transient): {e}")
                if attempt == self._max_retries - 1:
                    raise
                time.sleep(2 ** (attempt + 1))  # 2s, 4s, 8s
            except groq_lib.APIStatusError as e:
                self.logger.error(f"Groq API permanent error (status={e.status_code}): {e}")
                raise

    def evaluate_impact(self, news_batch: list[dict]) -> list[dict]:
        """Evaluate market impact processing news in safe chunks."""
        if not news_batch:
            return []

        chunk_size = 20
        all_processed_news = []

        for i in range(0, len(news_batch), chunk_size):
            chunk = news_batch[i : i + chunk_size]
            try:
                processed_chunk = self._process_scoring_chunk(chunk)
                all_processed_news.extend(processed_chunk)
            except Exception as e:
                self.logger.error(f"Failed to process scoring chunk {i}", exc_info=True)
                for item in chunk:
                    item["impact_score"] = 5
                    item["reason"] = f"Scoring error: {str(e)}"
                all_processed_news.extend(chunk)

        return all_processed_news

    def _process_scoring_chunk(self, chunk: list[dict]) -> list[dict]:
        """Send a single chunk to LLM and parse the JSON array response."""
        payload = [{"id": n["id"], "title": n["title"]} for n in chunk]

        prompt = (
            "Rate global IT market impact (1-10):\n"
            "- 10: Massive investments ($100B+), AI breakthroughs, critical security\n"
            "- 5: Major updates, new features\n"
            "- 1: Minor bug fixes\n"
            "Respond ONLY with valid JSON array of objects: "
            '[{"id": int, "impact_score": int, "reason": "short string"}]\n'
            f"Data: {json.dumps(payload, ensure_ascii=False)}"
        )

        response = self._call_groq_with_retry(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON using Regex
        json_match = re.search(r"\[.*?\]", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        # Safely parse JSON
        try:
            scores = json.loads(content)
            if not isinstance(scores, list):
                self.logger.error(f"LLM returned non-list JSON: {content}")
                scores = []
            elif not all(isinstance(item, dict) and "id" in item for item in scores):
                self.logger.error(f"LLM returned invalid JSON shape: {content}")
                scores = []
        except json.JSONDecodeError:
            self.logger.error(f"LLM returned invalid JSON: {content}")
            scores = []

        # Merge scores back to chunk with validation
        for news in chunk:
            score_data = next((item for item in scores if item.get("id") == news.get("id")), None)
            if score_data:
                # Validate and cast impact_score to int with bounds checking (1-10)
                raw_score = score_data.get("impact_score", 5)
                try:
                    impact_score = int(raw_score)
                    impact_score = max(1, min(10, impact_score))  # Clamp to 1-10
                except (ValueError, TypeError):
                    impact_score = 5
                news["impact_score"] = impact_score
                news["reason"] = score_data.get("reason", "No reason")
            else:
                news["impact_score"] = 5
                news["reason"] = "Not returned by AI"

        return chunk

    def generate_item_summaries(self, news_items: list[dict]) -> list[str]:
        """
        Generate one formatted Telegram message per news item.

        Each item is sent as a separate message to stay well within
        Telegram's 4096-character limit.
        """
        summaries = []
        for item in news_items:
            summaries.append(self._generate_single_summary(item))
        return summaries

    def _generate_single_summary(self, item: dict) -> str:
        """Call the LLM to produce a formatted Telegram message for one article."""
        prompt = (
            "You are an energetic, tech-savvy news anchor for a vibrant Kazakh IT community. "
            "Write a highly engaging and short IT news update in modern Kazakh based on this article:\n\n"
            f"Title: {item['title']}\n"
            f"Summary: {item.get('summary', '')}\n\n"
            "RULES FOR GENERATION:\n"
            "1. EMOJIS: Do NOT just use 🔥. "
            "Choose 1-2 emojis that perfectly match the topic "
            "(e.g., 🤖 for AI, 💰 for investments, 🛡️ for cybersecurity, 🚀 for startups, 🍎 for Apple).\n"
            "2. TONE: Professional yet conversational and engaging. "
            "Don't just translate; explain the impact like you are talking to fellow software engineers.\n"
            "3. FORMAT (Strict HTML, no links):\n"
            "[Contextual Emoji] <b>[Catchy and punchy title]</b>\n"
            "<blockquote>[2-3 sentences explaining what happened and WHY it "
            "matters to the tech world.]</blockquote>\n\n"
            "CRITICAL: Use ONLY Cyrillic alphabet (Kazakh). Translate tech terms naturally without sounding robotic."
        )
        system = (
            "Сіз IT және developer жаңалықтарын қазақ тілінде "
            "жазатын техникалық журналистсіз. Тек кириллица қолданыңыз!"
        )
        try:
            response = self._call_groq_with_retry(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=400,
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Single item summary failed: {e}")
            title = item.get("title", "")
            summary = item.get("summary", "")[:300]
            return f"<b>{title}</b>\n<blockquote>{summary}</blockquote>"


def create_ai_client() -> AIClient:
    """Factory function to create AI client based on provider."""
    if AI_PROVIDER.lower() == "groq":
        return GroqAIClient(api_key=GROQ_API_KEY)
    else:
        raise ValueError(f"Unsupported AI provider: {AI_PROVIDER}. Available: 'groq'")
