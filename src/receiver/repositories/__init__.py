import os

QUEUE_URL = os.environ.get("QUEUE_URL")

if not QUEUE_URL:
    raise ValueError("QUEUE_URL must be set")
