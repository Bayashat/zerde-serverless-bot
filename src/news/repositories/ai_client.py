"""AI client for generating news summaries with provider abstraction."""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

from aws_lambda_powertools import Logger
from groq import Groq


class AIClient(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def evaluate_impact(self, news_batch: list[dict]) -> list[dict]:
        """Rate global market impact of news (1-10 scale)."""
        pass

    @abstractmethod
    def generate_news_summary(self, news_items: list[dict], language: str = "kk") -> str:
        """Generate a formatted news summary in the specified language."""
        pass

    def _get_no_news_message(self, language: str) -> str:
        """Get 'no news' fallback message."""
        messages = {
            "kk": "📭 Бүгін жаңалық жоқ.",
            "ru": "📭 Сегодня новостей нет.",
            "en": "📭 No news today."
        }
        return messages.get(language, messages["en"])


class GroqAIClient(AIClient):
    """Groq AI provider implementation with chunking and resilient parsing."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Groq client."""
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required")
        self.client = Groq(api_key=self.api_key)
        self.logger = Logger()

    def evaluate_impact(self, news_batch: list[dict]) -> list[dict]:
        """Evaluate market impact processing news in safe chunks."""
        if not news_batch:
            return []

        chunk_size = 20
        all_processed_news = []
        
        for i in range(0, len(news_batch), chunk_size):
            chunk = news_batch[i:i + chunk_size]
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

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract JSON using Regex
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        
        # Safely parse JSON
        try:
            scores = json.loads(content)
        except json.JSONDecodeError:
            self.logger.error(f"LLM returned invalid JSON: {content}")
            scores = []
        
        # Merge scores back to chunk
        for news in chunk:
            score_data = next((item for item in scores if item.get("id") == news.get("id")), None)
            if score_data:
                news["impact_score"] = score_data.get("impact_score", 0)
                news["reason"] = score_data.get("reason", "No reason")
            else:
                news["impact_score"] = 5
                news["reason"] = "Not returned by AI"
                
        return chunk

    def generate_news_summary(self, news_items: list[dict], language: str = "kk") -> str:
        """Generate formatted news summary."""
        if not news_items:
            return self._get_no_news_message(language)

        news_text = "\n\n".join([
            f"Тақырып: {item['title']}\nСипаттама: {item.get('summary', 'Жоқ')}"
            for item in news_items[:3]
        ])

        prompt = self._build_prompt(news_text, language)

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "Сіз IT және developer жаңалықтарын қазақ тілінде жазатын техникалық журналистсіз. Тек өте маңызды және актуалды жаңалықтарды таңдаңыз."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1200,
            )

            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Summary generation failed: {e}")
            return f"❌ Қате орын алды: {str(e)}"

    def _build_prompt(self, news_text: str, language: str) -> str:
        """Construct the prompt template based on language."""
        if language == "kk":
            return f"""Мына IT жаңалықтарын қазақ тілінде қысқаша мазмұндаңыз. 
            
            МАҢЫЗДЫ ФОРМАТТАУ ЕРЕЖЕЛЕРІ:
            1. Тек 3 ең маңызды және қызықты жаңалықты таңдаңыз
            2. Developer және IT-қа қатысты мазмұнға басымдық беріңіз
            3. Сілтемелерді ҚОСПАҢЫЗ (оларды жібермеңіз)
            4. Цитата (blockquote) форматын пайдаланыңыз: <blockquote>Сипаттама</blockquote> - сипаттаманы HTML тегтерімен орап қойыңыз

            Форматы:
            🔥<b>Күннің IT жаңалықтары</b>

            <b>[Bold тақырып - қысқа және нақты]</b>
            <blockquote>Қысқаша сипаттама 2-3 сөйлем. Неге бұл маңызды? Әсері қандай?</blockquote>

            <b>[Bold тақырып]</b>
            <blockquote>Қысқаша сипаттама</blockquote>

            <b>[Bold тақырып]</b>  
            <blockquote>Қысқаша сипаттама</blockquote>

            Жаңалықтар:
            {news_text}

            Есте сақтаңыз:
            - Emoji пайдаланыңыз (🚀 🔥 💻 🤖 🔒 ⚡ etc)
            - Тақырыпты BOLD етіңіз: <b>Тақырып</b>
            - Сипаттаманы blockquote етіңіз: <blockquote>Сипаттама</blockquote>
            - Сілтемелерді ҚОСПАҢЫЗ
            - Тек ең маңызды 3 жаңалық"""
        else:
            return f"Summarize these IT news in {language}:\n{news_text}"


def create_ai_client(provider: str = "groq", api_key: Optional[str] = None) -> AIClient:
    """Factory function to create AI client based on provider."""
    if provider.lower() == "groq":
        return GroqAIClient(api_key=api_key)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}. Available: 'groq'")