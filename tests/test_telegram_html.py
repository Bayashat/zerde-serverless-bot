from services.ai.telegram_html import fit_llm_output, normalize_llm_output_for_telegram_html


def test_markdown_bold_italic_code_to_html() -> None:
    text = "This is **bold**, *italic*, and `code`."
    out = normalize_llm_output_for_telegram_html(text)
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert "<code>code</code>" in out


def test_raw_broken_html_is_escaped_before_markdown_conversion() -> None:
    text = "Bad <i>tag</code> but **markdown** and `x < y` are fine."

    out = normalize_llm_output_for_telegram_html(text)

    assert "&lt;i&gt;tag&lt;/code&gt;" in out
    assert "<b>markdown</b>" in out
    assert "<code>x &lt; y</code>" in out


def test_markdown_bullets_to_dot_bullets() -> None:
    text = "- first\n* second\n  - third"
    out = normalize_llm_output_for_telegram_html(text)
    assert out.splitlines() == ["• first", "• second", "• third"]


def test_fit_llm_output_trims_at_readable_boundary() -> None:
    text = "First sentence. Second sentence is useful. Third sentence is too much."

    out = fit_llm_output(text, max_chars=40)

    assert len(out) <= 40
    assert out.endswith("...")
    assert "Third sentence" not in out
