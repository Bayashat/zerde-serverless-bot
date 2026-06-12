from pathlib import Path


def test_bot_lambda_vector_policy_allows_metadata_query_dependencies() -> None:
    source = Path("infra/components/bot.py").read_text()

    assert '"s3vectors:QueryVectors"' in source
    assert '"s3vectors:GetVectors"' in source
