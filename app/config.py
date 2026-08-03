import os

from dotenv import load_dotenv


load_dotenv()


APP_VERSION = "1.0.0"
SPEC_VERSION = "1.0"

MAX_PAYLOAD_BYTES = 1_048_576
CHUNK_BYTES = 65_536
MAX_CONCURRENT_JOBS = 4
RATE_LIMIT_PER_MINUTE = 30

API_TOKEN = os.getenv(
    "API_TOKEN",
    "xsolla-intern-2026",
)