import os
from dotenv import load_dotenv

load_dotenv()

# Logging setup
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants from .env
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
RATE_LIMIT = int(os.getenv("RATE_LIMIT"))
TIME_WINDOW = int(os.getenv("TIME_WINDOW"))
DIRS = {
    "sessions": os.getenv("SESSIONS_DIR"),
    "data": os.getenv("DATA_DIR"),
    "photos": os.getenv("PHOTOS_DIR")
}
REPLY_INTERVAL = int(os.getenv("REPLY_INTERVAL"))
REPLY_THRESHOLD = int(os.getenv("REPLY_THRESHOLD"))
DEFAULT_DATA_PATH = os.getenv("DEFAULT_DATA_PATH")
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE"))

# Create directories
for dir_path in DIRS.values():
    os.makedirs(dir_path, exist_ok=True)