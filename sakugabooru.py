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

# Sakugabooru-compatible tag endpoint.
# Used only to verify whether a tag is actually an artist tag.
TAG_API = f"{BASE_URL}/tag.json"

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


# ============================================================
# TAG CATEGORIES
# ============================================================

# Different booru installations use slightly different
# category values, so we keep the known artist value here.
#
# On Danbooru-style systems:
#
# 0 = General
# 1 = Artist
# 3 = Copyright
# 4 = Character
# 5 = Meta
#
ARTIST_CATEGORY = 1


# ============================================================
# OBVIOUS NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # Characters / people
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

    # Generic
    "animated",
    "animation",
    "anime",
    "manga",
    "character",
    "characters",
    "background",
    "landscape",
    "scenery",

    # Media
    "screenshot",
    "official_art",
    "promotional_art",
    "cover",
    "video",
    "gif",
    "sound",
    "music",

    # Text
    "text",
    "english_text",
    "japanese_text",

    # Clothing
    "school_uniform",
    "uniform",
    "school",

    # Hair
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

    # Eyes
    "blue_eyes",
    "brown_eyes",
    "green_eyes",
    "red_eyes",
    "purple_eyes",

    # Objects
    "weapon",
    "sword",
    "gun",

    # Environment
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

    # Art
    "comic",
    "illustration",
    "art",
}


# ============================================================
# HELPERS
# ============================================================

def normalize_name(name: str) -> str:

    if not name:
        return ""

    name = str(name).strip()

    name = name.replace("_", " ")

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip()


def normalize_tag(tag: str) -> str:

    if not tag:
        return ""

    tag = str(tag).strip().lower()

    tag = tag.replace(" ", "_")

    tag = re.sub(
        r"_+",
        "_",
        tag,
    )

    return tag.strip("_")


def is_video_post(post: dict) -> bool:

    if not isinstance(post, dict):
        return False

    file_url = post.get("file_url")

    if not file_url:
        return False

    extension = post.get("file_ext")

    if extension:

        extension = str(
            extension
        ).lower().lstrip(".")

        if extension in VIDEO_EXTENSIONS:
            return True

    url = str(
        file_url
    ).lower()

    return (
        url.endswith(".mp4")
        or url.endswith(".webm")
    )


def post_url(post: dict) -> str | None:

    if not isinstance(post, dict):
        return None

    return post.get("file_url")


def extract_tags(post: dict) -> list[str]:

    if not isinstance(post, dict):
        return []

    # Some versions use "tags".
    tags = post.get("tags")

    # Some booru responses use "tag_string".
    if not tags:
        tags = post.get("tag_string", "")

    if isinstance(tags, list):

        return [
            normalize_tag(tag)
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


# ============================================================
# BASIC NAME CHECK
# ============================================================

def looks_like_name(tag: str) -> bool:
    """
    Basic sanity check only.

    IMPORTANT:
    This does NOT decide whether something is an animator.

    The actual animator decision is made by the Sakugabooru
    tag-category verification below.
    """

    tag = normalize_tag(tag)

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    if len(tag) < 5:
        return False

    if len(tag) > 60:
        return False

    if re.search(
        r"\d",
        tag,
    ):
        return False

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

    if len(parts) < 2:
        return False

    if any(
        len(part) > 30
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

        # Every clip used by this battle.
        self.used_clips: set[str] = set()

        # Clips used by each animator.
        self.animator_clips: dict[
            str,
            set[str],
        ] = {}

        # Last successful clip.
        self.last_clips: dict[
            str,
            dict,
        ] = {}

        # Animator -> posts.
        self.animator_cache: dict[
            str,
            list[dict],
        ] = {}

        # Tag -> category.
        self.tag_category_cache: dict[
            str,
            int | None,
        ] = {}

        # Tag -> verification result.
        self.artist_tag_cache: dict[
            str,
            bool,
        ] = {}

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
        url: str,
        params: dict | None = None,
    ):

        session = await self.get_session()

        try:

            async with session.get(
                url,
                params=params,
            ) as response:

                if response.status != 200:

                    print(
                        "Sakugabooru HTTP error:",
                        response.status,
                        url,
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
                "Sakugabooru request timed out:",
                url,
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
    # POSTS
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
            POST_API,
            params,
        )

        if not isinstance(data, list):
            return []

        return data

    # ========================================================
    # TAG INFORMATION
    # ========================================================

    async def get_tag_info(
        self,
        tag: str,
    ):
        """
        Ask Sakugabooru whether this tag is an artist tag.

        This is the important part that prevents:

            looney_tunes
            false_memory
            attack_on_titan

        from being treated as animator names simply because
        they contain underscores.
        """

        tag = normalize_tag(tag)

        if not tag:
            return None

        if tag in self.tag_category_cache:

            return self.tag_category_cache[
                tag
            ]

        # Try the common Danbooru-style endpoint first.
        params = {
            "name": tag,
            "limit": 10,
        }

        data = await self.request_json(
            TAG_API,
            params,
        )

        category = None

        # ----------------------------------------------------
        # RESPONSE CAN BE A LIST
        # ----------------------------------------------------

        if isinstance(data, list):

            for item in data:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                item_name = normalize_tag(
                    item.get(
                        "name",
                        "",
                    )
                )

                if item_name != tag:
                    continue

                raw_category = item.get(
                    "category"
                )

                try:

                    category = int(
                        raw_category
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    category = None

                break

        # ----------------------------------------------------
        # RESPONSE CAN BE A SINGLE OBJECT
        # ----------------------------------------------------

        elif isinstance(data, dict):

            item_name = normalize_tag(
                data.get(
                    "name",
                    "",
                )
            )

            if item_name == tag:

                raw_category = data.get(
                    "category"
                )

                try:

                    category = int(
                        raw_category
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    category = None

        self.tag_category_cache[
            tag
        ] = category

        return category

    # ========================================================
    # VERIFY ARTIST TAG
    # ========================================================

    async def is_artist_tag(
        self,
        tag: str,
    ) -> bool:
        """
        Return True only when Sakugabooru identifies the
        tag as an artist tag.

        No KFSL.
        No guessing from the name.
        """

        tag = normalize_tag(tag)

        if not tag:
            return False

        if tag in self.artist_tag_cache:

            return self.artist_tag_cache[
                tag
            ]

        if not looks_like_name(tag):

            self.artist_tag_cache[
                tag
            ] = False

            return False

        category = await self.get_tag_info(
            tag
        )

        result = (
            category == ARTIST_CATEGORY
        )

        self.artist_tag_cache[
            tag
        ] = result

        return result

    # ========================================================
    # RANDOM POST
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

        random.shuffle(
            posts
        )

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
    # ANIMATOR POSTS
    # ========================================================

    async def get_animator_posts(
        self,
        animator_name: str,
        limit: int = 100,
    ):

        tag = normalize_tag(
            animator_name
        )

        if not tag:
            return []

        if tag in self.animator_cache:

            return self.animator_cache[
                tag
            ]

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
    # FIND ANIMATOR FROM POST
    # ========================================================

    async def find_animator(
        self,
        tags,
    ):
        """
        Find an animator ONLY from Sakugabooru.

        We first find possible tags, then ask Sakugabooru
        whether each one is actually an artist tag.

        KFSL is not consulted.
        """

        if not tags:
            return None

        candidates = []

        for raw_tag in tags:

            tag = normalize_tag(
                raw_tag
            )

            if not tag:
                continue

            if not looks_like_name(tag):
                continue

            candidates.append(
                tag
            )

        if not candidates:
            return None

        random.shuffle(
            candidates
        )

        for candidate in candidates:

            # ----------------------------------------------
            # IMPORTANT:
            # Verify category first.
            # ----------------------------------------------

            if not await self.is_artist_tag(
                candidate
            ):
                continue

            posts = await self.get_animator_posts(
                candidate,
                limit=100,
            )

            if not posts:
                continue

            return {
                "name": normalize_name(
                    candidate
                ),
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
        """
        Kept only for compatibility.

        Tournament animator selection does NOT use this.
        """

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
        Get a Sakugabooru clip for an animator.

        RANDOM:
            Try a fresh clip.

        CONTINUOUS:
            Reuse the animator's existing clip.

        FALLBACK:
            If no new clip exists, use the animator's previous
            successful clip.
        """

        if not animator_name:
            return None

        animator_key = normalize_tag(
            animator_name
        )

        if not animator_key:
            return None

        previous_clip = self.last_clips.get(
            animator_key
        )

        # ----------------------------------------------------
        # CONTINUOUS
        # ----------------------------------------------------

        if (
            mode == "continuous"
            and previous_clip is not None
        ):

            return previous_clip

        # ----------------------------------------------------
        # GET CLIPS
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            animator_key,
            limit=100,
        )

        if not posts:

            # IMPORTANT:
            # Return old clip instead of breaking battle.
            return previous_clip

        posts = posts.copy()

        random.shuffle(
            posts
        )

        used_by_animator = (
            self.animator_clips.get(
                animator_key,
                set(),
            )
        )

        # ----------------------------------------------------
        # FIND UNUSED CLIP
        # ----------------------------------------------------

        for post in posts:

            url = post_url(
                post
            )

            if not url:
                continue

            if url in used_by_animator:
                continue

            if url in self.used_clips:
                continue

            clip = {
                "url": url,

                "id": post.get(
                    "id"
                ),

                "score": post.get(
                    "score",
                    0,
                ),

                "file_ext": post.get(
                    "file_ext"
                ),

                "tags": post.get(
                    "tags",
                    post.get(
                        "tag_string",
                        "",
                    ),
                ),
            }

            used_by_animator.add(
                url
            )

            self.animator_clips[
                animator_key
            ] = used_by_animator

            self.used_clips.add(
                url
            )

            self.last_clips[
                animator_key
            ] = clip

            return clip

        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------

        return previous_clip

    # ========================================================
    # DISCOVER ANIMATORS
    # ========================================================

    async def discover_animators(
        self,
        pages: int = 10,
    ):
        """
        Discover possible animator tags directly from
        Sakugabooru.

        IMPORTANT:

        We do NOT trust the spelling of the tag.

        Every candidate is checked against Sakugabooru's
        tag category before being accepted.
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

                tags = extract_tags(
                    post
                )

                for tag in tags:

                    if not looks_like_name(
                        tag
                    ):
                        continue

                    # Don't repeatedly add the same tag.
                    if tag not in candidates:

                        candidates[tag] = {
                            "name": normalize_name(
                                tag
                            ),

                            "tag": tag,

                            "posts": [],

                            "quality": 0.0,
                        }

                    candidates[
                        tag
                    ]["posts"].append(
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

                    if score > candidates[
                        tag
                    ]["quality"]:

                        candidates[
                            tag
                        ]["quality"] = score

        if not candidates:
            return []

        # ----------------------------------------------------
        # VERIFY AGAINST SAKUGABOORU
        # ----------------------------------------------------

        verified = []

        candidate_list = list(
            candidates.values()
        )

        random.shuffle(
            candidate_list
        )

        for candidate in candidate_list:

            tag = candidate[
                "tag"
            ]

            try:

                artist = await self.is_artist_tag(
                    tag
                )

            except Exception as e:

                print(
                    "Artist tag verification error:",
                    tag,
                    e,
                )

                artist = False

            if not artist:
                continue

            verified.append(
                candidate
            )

        return verified

    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate: dict,
    ):

        if not candidate:
            return False

        tag = candidate.get(
            "tag"
        )

        name = candidate.get(
            "name"
        )

        if not tag and name:

            tag = normalize_tag(
                name
            )

        if not tag:
            return False

        # ----------------------------------------------------
        # MUST BE AN ARTIST TAG
        # ----------------------------------------------------

        if not await self.is_artist_tag(
            tag
        ):

            return False

        # ----------------------------------------------------
        # MUST HAVE VIDEO POSTS
        # ----------------------------------------------------

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
        Choose tournament participants from Sakugabooru.

        There is NO KFSL dependency.

        The selection pipeline is:

            Sakugabooru posts
                    ↓
            possible tags
                    ↓
            Sakugabooru artist-category check
                    ↓
            usable video posts
                    ↓
            random weighted selection
                    ↓
            Animator objects in main.py
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # DISCOVER
        # ----------------------------------------------------

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
        # UNIQUE TAGS
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
        # WEIGHT
        # ----------------------------------------------------

        weighted = []

        for candidate in candidates:

            try:

                quality = float(
                    candidate.get(
                        "quality",
                        0,
                    )
                )

            except Exception:

                quality = 0.0

            # Higher score gives a small advantage,
            # but selection remains random.
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
                candidate[
                    "_weight"
                ]
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
                        candidate[
                            "_weight"
                        ]
                        for candidate in remaining
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
                    candidate.get(
                        "name"
                    ),
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

        self.used_clips.clear()

        self.animator_clips.clear()

        self.last_clips.clear()

        self.animator_cache.clear()

        self.tag_category_cache.clear()

        self.artist_tag_cache.clear()

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
# COMPATIBILITY HELPER
# ============================================================

async def get_random_post(
    difficulty: str = "extreme",
):

    client = SakugabooruClient()

    try:

        return await client.get_random_post(
            difficulty
        )

    finally:

        await client.close()