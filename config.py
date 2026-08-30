import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# DISCORD
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from .env")


# ============================================================
# BATTLE SETTINGS
# ============================================================

# Voting time for each matchup
VOTE_DURATION = 60

# Maximum number of animators allowed in one battle
MAX_ANIMATORS = 32

# Minimum number of animators
MIN_ANIMATORS = 2


# ============================================================
# SAKUGABOORU
# ============================================================

SAKUGABOORU_BASE_URL = "https://www.sakugabooru.com"

SAKUGABOORU_POST_API = (
    f"{SAKUGABOORU_BASE_URL}/post.json"
)

SAKUGABOORU_LIMIT = 100


# ============================================================
# CLIP SETTINGS
# ============================================================

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}

# Don't allow the same clip to be used twice
NO_DUPLICATE_CLIPS = True