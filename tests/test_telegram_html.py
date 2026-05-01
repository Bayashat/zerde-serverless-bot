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


def test_escapes_raw_html_control_characters() -> None:
    text = "Use x < y && y > 0 in <script>alert(1)</script>."
    out = normalize_llm_output_for_telegram_html(text)
    assert out == "Use x &lt; y &amp;&amp; y &gt; 0 in &lt;script&gt;alert(1)&lt;/script&gt;."


def test_markdown_formatting_escapes_inner_html() -> None:
    text = "**x < y** and `a & b`"
    out = normalize_llm_output_for_telegram_html(text)
    assert out == "<b>x &lt; y</b> and <code>a &amp; b</code>"
