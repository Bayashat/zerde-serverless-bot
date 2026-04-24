"""Rule-based spam pre-filter: fast, zero I/O scoring for incoming messages."""

import re

from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

# Compiled patterns — module-level for SnapStart warmth
_RE_MENTION = re.compile(r"@\w{3,}")
_RE_MONEY = re.compile(
    r"\$\d+|\d+р\b|\d+\s*(?:р\.|руб|тг|kzt|usd|eur|₸|₽)|доход.{0,10}\d+|заработ|выплат|оплат|дам\s*\d+",
    re.IGNORECASE,
)
_RE_VPN = re.compile(r"впн|vpn", re.IGNORECASE)
_RE_JOB = re.compile(r"работа|подработ|удалённо|удаленно|график|гибкий|гибкая|шабашк|шабаш", re.IGNORECASE)
_RE_DM_REDIRECT = re.compile(
    r"в\s*лс\b|в\s*личк|в\s*личные|пиши\s*(мне\s*)?в\s*лс|напишите\s*мне|пишите\s*мне",
    re.IGNORECASE,
)
_RE_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_RE_LATIN = re.compile(r"[a-zA-Z]")
_RE_WORD = re.compile(r"\S+")
_RE_URL = re.compile(r"t\.me/|telegram\.me/|https?://", re.IGNORECASE)
_RE_PROMO = re.compile(r"аренда|продаж|скидк|подписк|аккаунт|гаранти|отзыв|подключени", re.IGNORECASE)

_RE_SCAM_HOOK = re.compile(r"срочно|за пару (движений|минут)|быстрые деньги|легкие деньги", re.IGNORECASE)


class RuleBasedSpamFilter:
    """Layer-1 spam filter: returns a score 0.0–1.0 with triggered rule names."""

    def check(self, text: str, user_id: int, chat_id: int | str) -> tuple[float, list[str]]:
        """Return (score, triggered_rule_names). Score is capped at 1.0."""
        if not text:
            return 0.0, []

        score = 0.0
        triggered: list[str] = []

        has_mention = bool(_RE_MENTION.search(text))
        has_money = bool(_RE_MONEY.search(text))
        has_vpn = bool(_RE_VPN.search(text))
        has_job = bool(_RE_JOB.search(text))
        has_dm_redirect = bool(_RE_DM_REDIRECT.search(text))
        is_mixed_script = _has_mixed_script_word(text)
        has_url = bool(_RE_URL.search(text))
        has_promo = bool(_RE_PROMO.search(text))
        has_scam_hook = bool(_RE_SCAM_HOOK.search(text))

        # @username alone is normal group chat; only score as "external" with other risk signals
        risky_mention = has_mention and (has_money or has_vpn or has_job or is_mixed_script or has_url or has_promo)
        if risky_mention:
            score += 0.35
            triggered.append("external_mention")

        if has_url:
            score += 0.35
            triggered.append("external_url")

        if has_promo:
            score += 0.25
            triggered.append("promo_words")

        if has_money:
            score += 0.30
            triggered.append("money_pattern")

        if has_vpn:
            score += 0.35
            triggered.append("vpn_pattern")

        if has_job:
            score += 0.25
            triggered.append("job_offer")

        if is_mixed_script:
            score += 0.20
            triggered.append("cis_spam_obfuscation")

        if has_scam_hook:
            score += 0.25
            triggered.append("scam_hook")

        if has_money and has_scam_hook:
            score += 0.20
            triggered.append("money_and_scam_hook")

        if has_dm_redirect:
            score += 0.25
            triggered.append("dm_redirect")

        if has_money and has_dm_redirect:
            score += 0.20
            triggered.append("money_and_dm_redirect")

        if len(text) < 100 and risky_mention:
            score += 0.15
            triggered.append("short_text_with_contact")

        final_score = min(score, 1.0)
        if triggered:
            logger.debug(
                "Spam rules triggered",
                extra={"user_id": user_id, "chat_id": chat_id, "score": final_score, "rules": triggered},
            )
        return final_score, triggered


def _has_mixed_script_word(text: str) -> bool:
    """Return True if any single word contains both Cyrillic and Latin characters."""
    for word in _RE_WORD.findall(text):
        if _RE_CYRILLIC.search(word) and _RE_LATIN.search(word):
            return True
    return False
