from services.ai.telegram_html import normalize_llm_output_for_telegram_html


def test_markdown_bold_italic_code_to_html() -> None:
    text = "This is **bold**, *italic*, and `code`."
    out = normalize_llm_output_for_telegram_html(text)
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert "<code>code</code>" in out


def test_markdown_bullets_to_dot_bullets() -> None:
    text = "- first\n* second\n  - third"
    out = normalize_llm_output_for_telegram_html(text)
    assert out.splitlines() == ["• first", "• second", "• third"]
