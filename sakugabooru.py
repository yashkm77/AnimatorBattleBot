import asyncio
import aiohttp
import random
import re


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.sakugabooru.com"

POST_API = f"{BASE_URL}/post.json"

# Sakugabooru uses the Danbooru-style tag system.
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

# Standard booru artist category.
ARTIST_CATEGORY = 1


# ============================================================
# OBVIOUS NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # --------------------------------------------------------
    # PEOPLE / CHARACTER COUNTS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # GENERIC
    # --------------------------------------------------------

    "animated",
    "animation",
    "anime",
    "manga",

    "character",
    "characters",

    "background",
    "landscape",
    "scenery",

    # --------------------------------------------------------
    # MEDIA
    # --------------------------------------------------------

    "screenshot",
    "official_art",
    "promotional_art",
    "cover",

    "video",
    "gif",
    "sound",
    "music",

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    "text",
    "english_text",
    "japanese_text",

    # --------------------------------------------------------
    # CLOTHING
    # --------------------------------------------------------

    "school_uniform",
    "uniform",
    "school",

    # --------------------------------------------------------
    # HAIR
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # EYES
    # --------------------------------------------------------

    "blue_eyes",
    "brown_eyes",
    "green_eyes",
    "red_eyes",
    "purple_eyes",

    # --------------------------------------------------------
    # OBJECTS
    # --------------------------------------------------------

    "weapon",
    "sword",
    "gun",

    # --------------------------------------------------------
    # ENVIRONMENT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ART
    # --------------------------------------------------------

    "comic",
    "illustration",
    "art",

    # --------------------------------------------------------
    # BODY / POSE
    # --------------------------------------------------------

    "close_up",
    "full_body",
    "upper_body",
    "face",
    "profile",
    "front_view",
    "side_view",

    "looking_at_viewer",
    "looking_back",

    "smile",
    "open_mouth",
    "closed_eyes",
    "blush",
    "teeth",

    "hair",
    "eyes",
    "mouth",
    "hands",
    "feet",

    # --------------------------------------------------------
    # ACTION
    # --------------------------------------------------------

    "fighting",
    "action",
    "running",
    "walking",
    "jumping",
    "falling",
    "sitting",
    "standing",
    "lying",
    "dancing",

    "explosion",
    "fire",
    "smoke",
    "blood",
}


# ============================================================
# COMMON NON-ANIMATOR WORDS
# ============================================================

BLOCKED_WORDS = {
    "season",
    "episode",
    "opening",
    "ending",
    "movie",
    "special",
    "chapter",
    "version",
    "arc",
    "part",

    "character",
    "background",
    "camera",
    "effect",

    "school",
    "uniform",
    "weapon",

    "attack",
    "fight",
    "action",

    "sound",
    "music",

    "official",
    "promotional",

    "illustration",
    "animation",

    "art",
    "comic",

    "girl",
    "boy",
    "girls",
    "boys",

    "hair",
    "eyes",
    "mouth",
    "face",

    "background",
    "landscape",
    "scenery",

    "episode",
    "episodes",
}


# ============================================================
# KNOWN ANIME / FRANCHISE PREFIXES
# ============================================================

ANIME_PREFIXES = (
    "attack_on_",
    "jujutsu_",
    "my_hero_",
    "one_piece",
    "dragon_ball",
    "naruto_",
    "bleach_",
    "demon_slayer",
    "mobile_suit_",
    "fullmetal_",
    "hunter_x_",
    "sword_art_",
    "pokemon_",
    "fairy_tail",
    "black_clover",
    "chainsaw_man",
    "solo_leveling",
    "one_punch_",
    "fire_force",
    "vinland_saga",
    "blue_lock",
    "spy_x_",
    "frieren_",
    "boruto_",
    "jojo_",
    "dragon_quest",
    "detective_conan",
    "pretty_cure",
    "precure_",
    "sailor_moon",
    "evangelion",
    "gundam_",
    "macross_",
    "fate_",
    "pokemon",
)


# ============================================================
# HELPERS
# ============================================================

def normalize_name(
    name: str,
) -> str:

    if not name:
        return ""

    name = str(name).strip()

    name = name.replace(
        "_",
        " ",
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip()


def normalize_tag(
    tag: str,
) -> str:

    if not tag:
        return ""

    tag = str(tag).strip().lower()

    tag = tag.replace(
        " ",
        "_",
    )

    tag = re.sub(
        r"_+",
        "_",
        tag,
    )

    return tag.strip("_")


def is_video_post(
    post: dict,
) -> bool:

    if not isinstance(
        post,
        dict,
    ):
        return False

    file_url = post.get(
        "file_url"
    )

    if not file_url:
        return False

    extension = post.get(
        "file_ext"
    )

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


def post_url(
    post: dict,
) -> str | None:

    if not isinstance(
        post,
        dict,
    ):
        return None

    return post.get(
        "file_url"
    )


def extract_tags(
    post: dict,
) -> list[str]:

    if not isinstance(
        post,
        dict,
    ):
        return []

    tags = post.get(
        "tags"
    )

    if not tags:

        tags = post.get(
            "tag_string",
            "",
        )

    if isinstance(
        tags,
        list,
    ):

        result = []

        for tag in tags:

            normalized = normalize_tag(
                tag
            )

            if normalized:
                result.append(
                    normalized
                )

        return result

    if not isinstance(
        tags,
        str,
    ):
        return []

    result = []

    for tag in tags.split():

        normalized = normalize_tag(
            tag
        )

        if normalized:
            result.append(
                normalized
            )

    return result


# ============================================================
# NAME-LIKE FILTER
# ============================================================

def looks_like_name(
    tag: str,
) -> bool:
    """
    Preliminary filter only.

    This is NOT enough to make something an animator.

    Artist-category verification is preferred.
    """

    tag = normalize_tag(
        tag
    )

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    # Animator names normally have at least two words.
    if "_" not in tag:
        return False

    if len(tag) < 5:
        return False

    if len(tag) > 60:
        return False

    # Reject numbers.
    if re.search(
        r"\d",
        tag,
    ):
        return False

    # Only normal latin-style tags.
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

    # Avoid absurdly long words.
    if any(
        len(part) > 30
        for part in parts
    ):
        return False

    # Reject obvious non-person words.
    for part in parts:

        if part in BLOCKED_WORDS:
            return False

    # Reject obvious anime/franchise tags.
    for prefix in ANIME_PREFIXES:

        if tag.startswith(prefix):
            return False

    return True


# ============================================================
# SAKUGABOORU CLIENT
# ============================================================

class SakugabooruClient:

    def __init__(
        self,
    ):

        self.session = None

        # ----------------------------------------------------
        # Battle clip state
        # ----------------------------------------------------

        self.used_clips = set()

        self.animator_clips = {}

        self.last_clips = {}

        # ----------------------------------------------------
        # Caches
        # ----------------------------------------------------

        self.animator_cache = {}

        self.tag_category_cache = {}

        self.artist_tag_cache = {}

    # ========================================================
    # SESSION
    # ========================================================

    async def get_session(
        self,
    ):

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
        params=None,
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
                params,
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
        page=1,
        limit=100,
        tags=None,
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

        if not isinstance(
            data,
            list,
        ):

            return []

        return data

    # ========================================================
    # TAG INFO
    # ========================================================

    async def get_tag_info(
        self,
        tag: str,
    ):
        """
        Try to retrieve the Sakugabooru tag record.

        The important field is:

            category = 1

        which is the standard artist category.

        If the endpoint is unavailable, None is returned.
        """

        tag = normalize_tag(
            tag
        )

        if not tag:
            return None

        if tag in self.tag_category_cache:

            return self.tag_category_cache[
                tag
            ]

        # ----------------------------------------------------
        # First attempt: common Danbooru-style query
        # ----------------------------------------------------

        params = {
            "name": tag,
            "limit": 20,
        }

        data = await self.request_json(
            TAG_API,
            params,
        )

        category = None

        if isinstance(
            data,
            list,
        ):

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

        elif isinstance(
            data,
            dict,
        ):

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
    # ARTIST TAG CHECK
    # ========================================================

    async def is_artist_tag(
        self,
        tag: str,
    ) -> bool:
        """
        Determine whether a tag should be treated as an
        animator/artist.

        IMPORTANT:

        KFSL is never consulted here.
        """

        tag = normalize_tag(
            tag
        )

        if not tag:
            return False

        if tag in self.artist_tag_cache:

            return self.artist_tag_cache[
                tag
            ]

        if not looks_like_name(
            tag
        ):

            self.artist_tag_cache[
                tag
            ] = False

            return False

        # ----------------------------------------------------
        # Preferred verification: Sakugabooru tag category
        # ----------------------------------------------------

        category = await self.get_tag_info(
            tag
        )

        if category is not None:

            result = (
                category == ARTIST_CATEGORY
            )

            self.artist_tag_cache[
                tag
            ] = result

            return result

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------
        #
        # If Sakugabooru's tag endpoint does not work,
        # DON'T automatically trust every two-word tag.
        #
        # We require a real video search result.
        #
        # The candidate has already passed the strong
        # name-like filter above.
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        result = len(posts) > 0

        self.artist_tag_cache[
            tag
        ] = result

        return result

    # ========================================================
    # RANDOM POST
    # ========================================================

    async def get_random_post(
        self,
        difficulty="extreme",
    ):

        if difficulty == "easy":

            minimum_score = 40

        elif difficulty == "hard":

            minimum_score = 15

        else:

            minimum_score = None

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

            if not is_video_post(
                post
            ):
                continue

            if minimum_score is not None:

                try:

                    score = int(
                        post.get(
                            "score",
                            0,
                        )
                    )

                except Exception:

                    score = 0

                if score < minimum_score:
                    continue

            return post

        return None

    # ========================================================
    # ANIMATOR POSTS
    # ========================================================

    async def get_animator_posts(
        self,
        animator_name,
        limit=100,
    ):
        """
        Search for an exact Sakugabooru tag.

        Example:

            Yutaka Nakamura
                    ↓
            yutaka_nakamura
                    ↓
            post.json?tags=yutaka_nakamura
        """

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
    # FIND ANIMATOR
    # ========================================================

    async def find_animator(
        self,
        tags,
    ):
        """
        Find an animator from a post.

        ONLY Sakugabooru is used.

        Anime tags are never intentionally selected.
        """

        if not tags:
            return None

        candidates = []

        for raw_tag in tags:

            tag = normalize_tag(
                raw_tag
            )

            if not looks_like_name(
                tag
            ):
                continue

            candidates.append(
                tag
            )

        if not candidates:
            return None

        random.shuffle(
            candidates
        )

        for tag in candidates:

            if not await self.is_artist_tag(
                tag
            ):
                continue

            posts = await self.get_animator_posts(
                tag,
                limit=100,
            )

            if not posts:
                continue

            return {
                "name": normalize_name(
                    tag
                ),
                "tag": tag,
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
        Compatibility function.

        IMPORTANT:

        Tournament selection does NOT use anime tags.
        """

        return None

    # ========================================================
    # DISCOVER ANIMATORS
    # ========================================================

    async def discover_animators(
        self,
        pages=30,
    ):
        """
        Discover candidate artists from actual Sakugabooru
        video posts.

        Pipeline:

            video post
                ↓
            post tags
                ↓
            preliminary name filter
                ↓
            Sakugabooru artist category
                ↓
            usable video verification
        """

        pages = max(
            1,
            min(
                pages,
                100,
            ),
        )

        candidates = {}

        # ----------------------------------------------------
        # Random pages
        # ----------------------------------------------------

        page_numbers = list(
            range(
                1,
                pages + 1,
            )
        )

        random.shuffle(
            page_numbers
        )

        # ----------------------------------------------------
        # Collect tags
        # ----------------------------------------------------

        for page in page_numbers:

            posts = await self.get_posts(
                page=page,
                limit=100,
            )

            if not posts:
                continue

            for post in posts:

                if not is_video_post(
                    post
                ):
                    continue

                tags = extract_tags(
                    post
                )

                for tag in tags:

                    if not looks_like_name(
                        tag
                    ):
                        continue

                    if tag not in candidates:

                        candidates[
                            tag
                        ] = {
                            "name": normalize_name(
                                tag
                            ),

                            "tag": tag,

                            "quality": 0.0,

                            "post_count": 0,
                        }

                    candidates[
                        tag
                    ]["post_count"] += 1

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
        # Candidate order
        # ----------------------------------------------------

        candidate_list = list(
            candidates.values()
        )

        random.shuffle(
            candidate_list
        )

        # ----------------------------------------------------
        # Verify candidates
        # ----------------------------------------------------

        verified = []

        for candidate in candidate_list:

            tag = candidate.get(
                "tag"
            )

            if not tag:
                continue

            try:

                is_artist = await self.is_artist_tag(
                    tag
                )

            except Exception as e:

                print(
                    "Artist verification error:",
                    tag,
                    e,
                )

                is_artist = False

            if not is_artist:
                continue

            posts = await self.get_animator_posts(
                tag,
                limit=100,
            )

            if not posts:
                continue

            verified.append(
                {
                    "name": normalize_name(
                        tag
                    ),

                    "tag": tag,

                    "quality": candidate.get(
                        "quality",
                        0,
                    ),

                    "post_count": candidate.get(
                        "post_count",
                        0,
                    ),
                }
            )

        return verified

    # ========================================================
    # CHOOSE BATTLE ANIMATORS
    # ========================================================

    async def choose_battle_animators(
        self,
        count,
    ):
        """
        Choose tournament participants.

        SOURCE:

            Sakugabooru

        NOT:

            KFSL
            anime database
            anime tags

        KFSL can be used elsewhere in your project for
        optional animator information, but it is completely
        absent from tournament selection.
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # DISCOVERY
        # ----------------------------------------------------

        # More pages = better candidate pool.
        discovery_pages = max(
            30,
            min(
                100,
                count * 8,
            ),
        )

        candidates = await self.discover_animators(
            pages=discovery_pages
        )

        if not candidates:

            print(
                "Sakugabooru returned no verified "
                "animator candidates."
            )

            return []

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
        # WEIGHTED RANDOM
        # ----------------------------------------------------
        #
        # We don't simply choose the highest-score names.
        #
        # A higher-quality animator gets a small advantage,
        # while the tournament remains random.
        # ----------------------------------------------------

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

            try:

                post_count = int(
                    candidate.get(
                        "post_count",
                        0,
                    )
                )

            except Exception:

                post_count = 0

            quality_weight = min(
                max(
                    quality + 10.0,
                    1.0,
                ),
                100.0,
            )

            # Small bonus for having multiple clips.
            clip_bonus = min(
                post_count,
                20,
            ) * 0.5

            candidate[
                "_weight"
            ] = (
                quality_weight
                + clip_bonus
            )

        # ----------------------------------------------------
        # SELECT
        # ----------------------------------------------------

        selected = []

        remaining = candidates.copy()

        while (
            remaining
            and len(selected) < count
        ):

            weights = [
                max(
                    1.0,
                    float(
                        candidate.get(
                            "_weight",
                            1.0,
                        )
                    ),
                )
                for candidate in remaining
            ]

            candidate = random.choices(
                remaining,
                weights=weights,
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

            tag = candidate.get(
                "tag"
            )

            if not tag:
                continue

            try:

                valid = await self.verify_animator(
                    candidate
                )

            except Exception as e:

                print(
                    "Final animator verification error:",
                    tag,
                    e,
                )

                valid = False

            if not valid:
                continue

            verified.append(
                {
                    "name": normalize_name(
                        tag
                    ),

                    "tag": tag,

                    "quality": candidate.get(
                        "quality",
                        0,
                    ),
                }
            )

        # ----------------------------------------------------
        # IF RANDOM SELECTION LOST CANDIDATES
        # ----------------------------------------------------
        #
        # Fill remaining slots from the rest of the verified
        # pool.
        # ----------------------------------------------------

        if len(verified) < count:

            selected_tags = {
                item["tag"]
                for item in verified
            }

            fallback_candidates = [
                candidate
                for candidate in candidates
                if candidate.get(
                    "tag"
                ) not in selected_tags
            ]

            random.shuffle(
                fallback_candidates
            )

            for candidate in fallback_candidates:

                if len(verified) >= count:
                    break

                try:

                    valid = await self.verify_animator(
                        candidate
                    )

                except Exception:

                    valid = False

                if not valid:
                    continue

                tag = candidate.get(
                    "tag"
                )

                if not tag:
                    continue

                verified.append(
                    {
                        "name": normalize_name(
                            tag
                        ),

                        "tag": tag,

                        "quality": candidate.get(
                            "quality",
                            0,
                        ),
                    }
                )

        return verified[:count]

    # ========================================================
    # BATTLE CLIP
    # ========================================================

    async def get_battle_clip(
        self,
        animator_name,
        mode="random",
    ):
        """
        Get a usable clip for an animator.
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
        # FIND NEW CLIP
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
    # RESET
    # ========================================================

    def reset(
        self,
    ):

        self.used_clips.clear()

        self.animator_clips.clear()

        self.last_clips.clear()

        self.animator_cache.clear()

        self.tag_category_cache.clear()

        self.artist_tag_cache.clear()

    # ========================================================
    # CLOSE
    # ========================================================

    async def close(
        self,
    ):

        if (
            self.session is not None
            and not self.session.closed
        ):

            await self.session.close()

        self.session = None

    # ========================================================
    # CONTEXT MANAGER
    # ========================================================

    async def __aenter__(
        self,
    ):

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
    difficulty="extreme",
):

    client = SakugabooruClient()

    try:

        return await client.get_random_post(
            difficulty
        )

    finally:

        await client.close()