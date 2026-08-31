import asyncio
import aiohttp
import random
import re
from urllib.parse import quote


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.sakugabooru.com"

POST_API = f"{BASE_URL}/post.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/26.0 Safari/605.1.15"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/plain,*/*",
}

REQUEST_TIMEOUT = 20

MAX_POST_PAGES = 3000

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}

# Tags that are clearly not animator names.
# These are filtered when discovering candidates.
IGNORED_TAGS = {
    "1girl",
    "1boy",
    "2girls",
    "2boys",
    "3girls",
    "3boys",
    "4girls",
    "4boys",
    "5girls",
    "5boys",
    "6girls",
    "6boys",
    "7girls",
    "7boys",
    "8girls",
    "8boys",

    "male",
    "female",
    "solo",
    "duo",
    "group",
    "multiple_girls",
    "multiple_boys",

    "animated",
    "animation",
    "anime",
    "manga",

    "character",
    "characters",
    "background",
    "landscape",
    "scenery",

    "screenshot",
    "official_art",
    "promotional_art",
    "cover",

    "video",
    "gif",
    "sound",
    "music",

    "text",
    "english_text",
    "japanese_text",

    "school_uniform",
    "uniform",
    "school",

    "long_hair",
    "short_hair",
    "black_hair",
    "brown_hair",
    "blonde_hair",
    "blue_hair",
    "red_hair",
    "pink_hair",
    "green_hair",
    "purple_hair",
    "white_hair",

    "blue_eyes",
    "brown_eyes",
    "green_eyes",
    "red_eyes",
    "purple_eyes",

    "weapon",
    "sword",
    "gun",

    "day",
    "night",
    "indoors",
    "outdoors",

    "simple_background",
    "gradient_background",

    "reflection",
    "water",
    "sky",
    "cloud",

    "comic",
    "illustration",
    "art",
}


# ============================================================
# HELPERS
# ============================================================

def normalize_name(name: str) -> str:
    """
    Convert a Sakugabooru tag into a readable animator name.

    Example:

        yutaka_nakamura
        ->
        Yutaka Nakamura
    """

    if not name:
        return ""

    name = name.strip()

    name = name.replace("_", " ")

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip()


def normalize_tag(tag: str) -> str:
    """
    Normalize a Sakugabooru tag.
    """

    if not tag:
        return ""

    tag = tag.strip().lower()

    tag = tag.replace(" ", "_")

    tag = re.sub(
        r"_+",
        "_",
        tag,
    )

    return tag


def is_video_post(post: dict) -> bool:
    """
    Check whether a Sakugabooru post is a usable video.
    """

    if not isinstance(post, dict):
        return False

    file_url = post.get("file_url")

    if not file_url:
        return False

    extension = post.get("file_ext")

    if extension:
        extension = extension.lower().lstrip(".")

        if extension in VIDEO_EXTENSIONS:
            return True

    # Fallback to URL extension.
    url = file_url.lower()

    return (
        url.endswith(".mp4")
        or url.endswith(".webm")
    )


def post_url(post: dict) -> str | None:
    """
    Get the direct media URL from a post.
    """

    if not isinstance(post, dict):
        return None

    url = post.get("file_url")

    if not url:
        return None

    return url


def extract_tags(post: dict) -> list[str]:
    """
    Extract tags from a Sakugabooru post.

    Sakugabooru normally provides tags as one space-separated
    string.
    """

    tags = post.get("tags", "")

    if isinstance(tags, list):
        return [
            normalize_tag(str(tag))
            for tag in tags
            if tag
        ]

    if not isinstance(tags, str):
        return []

    return [
        normalize_tag(tag)
        for tag in tags.split()
        if tag
    ]


def looks_like_animator_tag(tag: str) -> bool:
    """
    Try to determine whether a tag could be an animator name.

    This is intentionally conservative.

    It rejects obvious character/anime/general tags,
    while allowing names such as:

        yutaka_nakamura
        keiichiro_watanabe
        weilin_zhang
    """

    tag = normalize_tag(tag)

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    # Avoid extremely short tags.
    if len(tag) < 5:
        return False

    # Animator tags normally contain an underscore.
    if "_" not in tag:
        return False

    # Don't accept huge tags.
    if len(tag) > 50:
        return False

    # Avoid obvious numeric tags.
    if re.search(
        r"\d",
        tag,
    ):
        return False

    # Avoid obvious non-name patterns.
    blocked_patterns = (
        "season",
        "episode",
        "movie",
        "opening",
        "ending",
        "chapter",
        "version",
        "character_",
        "weapon_",
        "school_",
        "uniform_",
        "background_",
        "camera_",
        "effect_",
        "special_",
    )

    for pattern in blocked_patterns:

        if tag.startswith(pattern):

            return False

    # A name-like tag should consist mostly of letters
    # and underscores.
    if not re.fullmatch(
        r"[a-z_]+",
        tag,
    ):

        return False

    parts = [
        part
        for part in tag.split("_")
        if part
    ]

    # Most animator names have at least two parts.
    if len(parts) < 2:
        return False

    # Don't accept absurdly long individual words.
    if any(
        len(part) > 25
        for part in parts
    ):
        return False

    return True


# ============================================================
# SAKUGABOORU CLIENT
# ============================================================

class SakugabooruClient:

    def __init__(self):

        self.session: aiohttp.ClientSession | None = None

        # Clips already returned during this tournament.
        self.used_clips: set[str] = set()

        # Clips previously used by individual animators.
        self.animator_clips: dict[str, set[str]] = {}

        # Last successful clip for fallback.
        self.last_clips: dict[str, dict] = {}

        # Cache animator -> posts.
        self.animator_cache: dict[str, list[dict]] = {}

        # Cache tag -> result.
        self.tag_cache: dict[str, list[dict]] = {}

    # ========================================================
    # SESSION
    # ========================================================

    async def get_session(self):

        if (
            self.session is None
            or self.session.closed
        ):

            timeout = aiohttp.ClientTimeout(
                total=REQUEST_TIMEOUT
            )

            self.session = aiohttp.ClientSession(
                headers=HEADERS,
                timeout=timeout,
            )

        return self.session

    # ========================================================
    # REQUEST
    # ========================================================

    async def request_json(
        self,
        params: dict,
    ):

        session = await self.get_session()

        try:

            async with session.get(
                POST_API,
                params=params,
            ) as response:

                if response.status != 200:

                    print(
                        "Sakugabooru HTTP error:",
                        response.status,
                        params,
                    )

                    return None

                try:

                    return await response.json(
                        content_type=None
                    )

                except Exception as e:

                    print(
                        "Sakugabooru JSON error:",
                        e,
                    )

                    return None

        except asyncio.TimeoutError:

            print(
                "Sakugabooru request timed out."
            )

            return None

        except aiohttp.ClientError as e:

            print(
                "Sakugabooru request error:",
                e,
            )

            return None

        except Exception as e:

            print(
                "Unexpected Sakugabooru error:",
                e,
            )

            return None

    # ========================================================
    # GET POSTS
    # ========================================================

    async def get_posts(
        self,
        page: int = 1,
        limit: int = 100,
        tags: str | None = None,
    ):

        params = {
            "page": page,
            "limit": limit,
        }

        if tags:

            params["tags"] = tags

        data = await self.request_json(
            params
        )

        if not isinstance(data, list):

            return []

        return data

    # ========================================================
    # GET RANDOM POST
    # ========================================================

    async def get_random_post(
        self,
        difficulty: str = "extreme",
    ):

        if difficulty == "easy":

            min_score = 40

        elif difficulty == "hard":

            min_score = 15

        else:

            min_score = None

        page = random.randint(
            1,
            MAX_POST_PAGES,
        )

        posts = await self.get_posts(
            page=page,
            limit=100,
        )

        if not posts:

            return None

        random.shuffle(posts)

        for post in posts:

            if not is_video_post(post):

                continue

            if min_score is not None:

                try:

                    score = int(
                        post.get(
                            "score",
                            0,
                        )
                    )

                except Exception:

                    score = 0

                if score < min_score:

                    continue

            return post

        return None

    # ========================================================
    # GET POSTS FOR ANIMATOR
    # ========================================================

    async def get_animator_posts(
        self,
        animator_name: str,
        limit: int = 100,
    ):

        tag = normalize_tag(
            animator_name
        )

        if tag in self.animator_cache:

            return self.animator_cache[tag]

        posts = await self.get_posts(
            page=1,
            limit=limit,
            tags=tag,
        )

        video_posts = [
            post
            for post in posts
            if is_video_post(post)
        ]

        self.animator_cache[
            tag
        ] = video_posts

        return video_posts

    # ========================================================
    # FIND ANIMATOR
    # ========================================================

    async def find_animator(
        self,
        tags,
    ):
        """
        Find a likely animator tag from a post's tags.

        This does NOT use KFSL.

        It only uses the tags supplied by Sakugabooru.
        """

        if not tags:

            return None

        candidates = []

        for tag in tags:

            tag = normalize_tag(tag)

            if not looks_like_animator_tag(tag):

                continue

            candidates.append(tag)

        if not candidates:

            return None

        # Randomize instead of always choosing the first
        # possible name.
        random.shuffle(candidates)

        for candidate in candidates:

            posts = await self.get_animator_posts(
                candidate,
                limit=100,
            )

            if not posts:

                continue

            return {
                "name": normalize_name(candidate),
                "tag": candidate,
            }

        return None

    # ========================================================
    # FIND ANIME
    # ========================================================

    async def find_anime(
        self,
        tags,
    ):

        if not tags:

            return None

        # Anime identification is intentionally lightweight.
        #
        # We don't need anime names for tournament selection,
        # but this keeps compatibility with code that may use
        # find_anime().

        for tag in tags:

            tag = normalize_tag(tag)

            if not tag:
                continue

            if tag in IGNORED_TAGS:
                continue

            if tag.endswith(
                "_season"
            ):
                continue

        return None

    # ========================================================
    # BATTLE CLIP
    # ========================================================

    async def get_battle_clip(
        self,
        animator_name: str,
        mode: str = "random",
    ):
        """
        Get a clip for an animator.

        random:
            Try to give a new clip.

        continuous:
            Keep using the animator's current clip.

        If a new clip cannot be found, return the previous
        successful clip as a fallback.
        """

        if not animator_name:

            return None

        animator_key = normalize_tag(
            animator_name
        )

        previous_clip = self.last_clips.get(
            animator_key
        )

        # ----------------------------------------------------
        # CONTINUOUS MODE
        # ----------------------------------------------------

        if (
            mode == "continuous"
            and previous_clip is not None
        ):

            return previous_clip

        # ----------------------------------------------------
        # GET POSTS
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            animator_key,
            limit=100,
        )

        if not posts:

            return previous_clip

        # ----------------------------------------------------
        # SHUFFLE
        # ----------------------------------------------------

        posts = posts.copy()

        random.shuffle(posts)

        used_by_animator = self.animator_clips.get(
            animator_key,
            set(),
        )

        # ----------------------------------------------------
        # TRY UNUSED CLIP
        # ----------------------------------------------------

        for post in posts:

            url = post_url(post)

            if not url:
                continue

            # Don't use a clip this animator already used.
            if url in used_by_animator:

                continue

            # Don't reuse a clip globally if another animator
            # somehow points to the same media.
            if url in self.used_clips:

                continue

            clip = {
                "url": url,
                "id": post.get("id"),
                "score": post.get("score", 0),
                "file_ext": post.get(
                    "file_ext"
                ),
                "tags": post.get(
                    "tags",
                    "",
                ),
            }

            used_by_animator.add(url)

            self.animator_clips[
                animator_key
            ] = used_by_animator

            self.used_clips.add(url)

            self.last_clips[
                animator_key
            ] = clip

            return clip

        # ----------------------------------------------------
        # NO NEW CLIP
        # ----------------------------------------------------

        # Important:
        #
        # Do NOT fail the tournament.
        #
        # Reuse the animator's previous successful clip.
        return previous_clip

    # ========================================================
    # DISCOVER ANIMATORS FROM SAKUGABOORU
    # ========================================================

    async def discover_animators(
        self,
        pages: int = 10,
    ):
        """
        Discover animator candidates directly from
        Sakugabooru video posts.

        No KFSL is used.
        """

        candidates = {}

        pages = max(
            1,
            min(
                pages,
                100,
            ),
        )

        page_numbers = list(
            range(
                1,
                pages + 1,
            )
        )

        random.shuffle(
            page_numbers
        )

        for page in page_numbers:

            posts = await self.get_posts(
                page=page,
                limit=100,
            )

            if not posts:

                continue

            for post in posts:

                if not is_video_post(post):

                    continue

                tags = extract_tags(post)

                for tag in tags:

                    if not looks_like_animator_tag(tag):

                        continue

                    name = normalize_name(tag)

                    if not name:

                        continue

                    if tag not in candidates:

                        candidates[tag] = {
                            "name": name,
                            "tag": tag,
                            "posts": [],
                            "quality": 0.0,
                        }

                    candidates[tag]["posts"].append(
                        post
                    )

                    try:

                        score = float(
                            post.get(
                                "score",
                                0,
                            )
                        )

                    except Exception:

                        score = 0.0

                    if score > candidates[tag]["quality"]:

                        candidates[tag]["quality"] = score

        return list(
            candidates.values()
        )

    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate: dict,
    ):
        """
        Verify that an animator actually has usable
        Sakugabooru video clips.
        """

        if not candidate:

            return False

        tag = candidate.get(
            "tag"
        )

        name = candidate.get(
            "name"
        )

        if not tag and name:

            tag = normalize_tag(name)

        if not tag:

            return False

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        return len(posts) > 0

    # ========================================================
    # CHOOSE BATTLE ANIMATORS
    # ========================================================

    async def choose_battle_animators(
        self,
        count: int,
    ):
        """
        Choose tournament participants exclusively from
        Sakugabooru.

        KFSL is NOT used.

        Every selected animator must have at least one
        usable video post on Sakugabooru.
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # DISCOVER
        # ----------------------------------------------------

        # Search several pages so small/rare names have
        # a better chance of appearing.
        discovery_pages = max(
            10,
            min(
                100,
                count * 5,
            ),
        )

        candidates = await self.discover_animators(
            pages=discovery_pages
        )

        if not candidates:

            return []

        # ----------------------------------------------------
        # SHUFFLE
        # ----------------------------------------------------

        random.shuffle(
            candidates
        )

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        unique = {}

        for candidate in candidates:

            tag = normalize_tag(
                candidate.get(
                    "tag",
                    "",
                )
            )

            if not tag:

                continue

            unique[tag] = candidate

        candidates = list(
            unique.values()
        )

        # ----------------------------------------------------
        # SORT A LITTLE BY QUALITY
        # ----------------------------------------------------
        #
        # Don't simply choose the highest-scoring animators,
        # because that would make every tournament nearly
        # identical.
        #
        # Instead, give higher-quality candidates a slightly
        # better chance while retaining randomness.

        weighted = []

        for candidate in candidates:

            quality = candidate.get(
                "quality",
                0,
            )

            try:

                quality = float(
                    quality
                )

            except Exception:

                quality = 0.0

            # Clamp weight.
            weight = max(
                1.0,
                min(
                    quality + 10.0,
                    100.0,
                ),
            )

            candidate[
                "_weight"
            ] = weight

            weighted.append(
                candidate
            )

        # ----------------------------------------------------
        # SELECT
        # ----------------------------------------------------

        selected = []

        remaining = weighted.copy()

        while (
            remaining
            and len(selected) < count
        ):

            total_weight = sum(
                candidate["_weight"]
                for candidate in remaining
            )

            if total_weight <= 0:

                candidate = random.choice(
                    remaining
                )

            else:

                candidate = random.choices(
                    remaining,
                    weights=[
                        c["_weight"]
                        for c in remaining
                    ],
                    k=1,
                )[0]

            selected.append(
                candidate
            )

            remaining.remove(
                candidate
            )

        # ----------------------------------------------------
        # FINAL VERIFICATION
        # ----------------------------------------------------

        verified = []

        for candidate in selected:

            try:

                valid = await self.verify_animator(
                    candidate
                )

            except Exception as e:

                print(
                    "Animator verification error:",
                    candidate.get("name"),
                    e,
                )

                valid = False

            if not valid:

                continue

            verified.append(
                {
                    "name": candidate[
                        "name"
                    ],

                    "tag": candidate[
                        "tag"
                    ],

                    "quality": candidate.get(
                        "quality",
                        0,
                    ),
                }
            )

            if len(verified) >= count:

                break

        return verified

    # ========================================================
    # RESET
    # ========================================================

    def reset(self):
        """
        Reset tournament clip state.

        The HTTP session is intentionally left open until
        close() is called.
        """

        self.used_clips.clear()

        self.animator_clips.clear()

        self.last_clips.clear()

        self.animator_cache.clear()

        self.tag_cache.clear()

    # ========================================================
    # CLOSE
    # ========================================================

    async def close(self):

        if (
            self.session is not None
            and not self.session.closed
        ):

            await self.session.close()

        self.session = None

    # ========================================================
    # CONTEXT MANAGER
    # ========================================================

    async def __aenter__(self):

        await self.get_session()

        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ):

        await self.close()


# ============================================================
# COMPATIBILITY HELPERS
# ============================================================

async def get_random_post(
    difficulty: str = "extreme",
):
    """
    Convenience function for code that previously imported
    get_random_post directly.
    """

    client = SakugabooruClient()

    try:

        return await client.get_random_post(
            difficulty
        )

    finally:

        await client.close()