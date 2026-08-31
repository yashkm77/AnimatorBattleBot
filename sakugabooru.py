import asyncio
import aiohttp
import random
import re


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.sakugabooru.com"

POST_API = f"{BASE_URL}/post.json"
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

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}

ARTIST_CATEGORY = 1


# ============================================================
# OBVIOUS NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # people / counts
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

    # generic
    "animated",
    "animation",
    "anime",
    "manga",
    "character",
    "characters",

    "background",
    "landscape",
    "scenery",

    # media
    "screenshot",
    "official_art",
    "promotional_art",
    "cover",
    "video",
    "gif",
    "sound",
    "music",

    # text
    "text",
    "english_text",
    "japanese_text",

    # clothing
    "school_uniform",
    "uniform",
    "school",

    # hair
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

    # eyes
    "blue_eyes",
    "brown_eyes",
    "green_eyes",
    "red_eyes",
    "purple_eyes",

    # objects
    "weapon",
    "sword",
    "gun",

    # environment
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

    # art
    "comic",
    "illustration",
    "art",

    # body / pose
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

    # action
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
# COMMON NON-PERSON WORDS
# ============================================================

BLOCKED_WORDS = {
    # anime / media
    "season",
    "seasons",
    "episode",
    "episodes",
    "opening",
    "ending",
    "movie",
    "movies",
    "special",
    "specials",
    "chapter",
    "version",
    "arc",
    "part",
    "series",

    # production / generic
    "production",
    "materials",
    "material",
    "camera",
    "effect",
    "effects",
    "background",

    # animation terms
    "animation",
    "animator",
    "animators",
    "director",
    "directors",
    "staff",
    "studio",
    "key",
    "frame",
    "frames",

    # generic subjects
    "character",
    "characters",
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

    "landscape",
    "scenery",

    "background",

    # common booru concepts
    "series",
    "project",
    "layout",
    "design",
    "designer",
    "mechanical",
    "mecha",
    "logo",
    "title",
    "credits",
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
    "tiger_mask",
    "tiger_mask_series",
)


# ============================================================
# KNOWN NON-PERSON PATTERNS
# ============================================================

NON_PERSON_PATTERNS = (
    r"^.*_series$",
    r"^.*_season$",
    r"^.*_season_\d+$",
    r"^.*_episode$",
    r"^.*_episode_\d+$",
    r"^.*_opening$",
    r"^.*_ending$",
    r"^.*_movie$",
    r"^.*_special$",
    r"^.*_materials$",
    r"^.*_material$",
    r"^.*_version$",
    r"^.*_arc$",
    r"^.*_project$",
)


# ============================================================
# HELPERS
# ============================================================

def normalize_name(name: str) -> str:

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


def normalize_tag(tag: str) -> str:

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


def is_video_post(post: dict) -> bool:

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


def post_url(post: dict):

    if not isinstance(
        post,
        dict,
    ):
        return None

    return post.get(
        "file_url"
    )


def extract_tags(post: dict) -> list[str]:

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
# NAME FILTER
# ============================================================

def looks_like_name(tag: str) -> bool:

    tag = normalize_tag(
        tag
    )

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    if "_" not in tag:
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

    for part in parts:

        if part in BLOCKED_WORDS:
            return False

    for prefix in ANIME_PREFIXES:

        if tag.startswith(prefix):
            return False

    for pattern in NON_PERSON_PATTERNS:

        if re.match(
            pattern,
            tag,
        ):
            return False

    return True


# ============================================================
# SAKUGABOORU CLIENT
# ============================================================

class SakugabooruClient:

    def __init__(self):

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
        # Sakugabooru tag endpoint
        # ----------------------------------------------------

        data = await self.request_json(
            TAG_API,
            {
                "name": tag,
                "limit": 100,
            },
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

                try:

                    category = int(
                        item.get(
                            "category"
                        )
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

                try:

                    category = int(
                        data.get(
                            "category"
                        )
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
    # ARTIST TAG
    # ========================================================

    async def is_artist_tag(
        self,
        tag: str,
    ) -> bool:

        tag = normalize_tag(
            tag
        )

        if not tag:
            return False

        if tag in self.artist_tag_cache:

            return self.artist_tag_cache[
                tag
            ]

        # ----------------------------------------------------
        # Fast rejection
        # ----------------------------------------------------

        if not looks_like_name(
            tag
        ):

            self.artist_tag_cache[
                tag
            ] = False

            return False

        # ----------------------------------------------------
        # Ask Sakugabooru
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
        # No category information
        #
        # IMPORTANT:
        # Do NOT automatically trust the tag.
        #
        # Only use a conservative fallback.
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:

            self.artist_tag_cache[
                tag
            ] = False

            return False

        # Require at least one real video.
        has_video = any(
            is_video_post(post)
            for post in posts
        )

        if not has_video:

            self.artist_tag_cache[
                tag
            ] = False

            return False

        # Stronger person-name heuristic.
        parts = tag.split("_")

        # Reject obviously descriptive phrases.
        descriptive_words = {
            "series",
            "production",
            "materials",
            "material",
            "project",
            "episode",
            "season",
            "opening",
            "ending",
            "movie",
            "special",
            "version",
            "arc",
            "part",
            "character",
            "background",
            "animation",
            "art",
            "music",
            "sound",
            "studio",
            "school",
        }

        if any(
            part in descriptive_words
            for part in parts
        ):

            self.artist_tag_cache[
                tag
            ] = False

            return False

        self.artist_tag_cache[
            tag
        ] = True

        return True

    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate,
    ) -> bool:
        """
        Final safety check before a name enters a battle.

        candidate may be:

            {
                "name": "...",
                "tag": "..."
            }

        or simply a string.
        """

        if isinstance(
            candidate,
            dict,
        ):

            tag = candidate.get(
                "tag"
            )

            if not tag:

                tag = candidate.get(
                    "name"
                )

        else:

            tag = candidate

        tag = normalize_tag(
            tag
        )

        if not tag:
            return False

        # ----------------------------------------------------
        # Basic filter
        # ----------------------------------------------------

        if not looks_like_name(
            tag
        ):
            return False

        # ----------------------------------------------------
        # Artist category verification
        # ----------------------------------------------------

        if not await self.is_artist_tag(
            tag
        ):
            return False

        # ----------------------------------------------------
        # Actual video verification
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:
            return False

        video_count = 0

        for post in posts:

            if is_video_post(
                post
            ):
                video_count += 1

                if video_count >= 1:
                    break

        if video_count == 0:
            return False

        return True

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

        # Try a few random pages instead of failing
        # immediately on one empty page.

        for _ in range(5):

            page = random.randint(
                1,
                3000,
            )

            posts = await self.get_posts(
                page=page,
                limit=100,
            )

            if not posts:
                continue

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

        video_posts = []

        for post in posts:

            if is_video_post(
                post
            ):

                video_posts.append(
                    post
                )

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

        # Kept for compatibility with older code.
        return None

    # ========================================================
    # DISCOVER ANIMATORS
    # ========================================================

    async def discover_animators(
        self,
        pages=12,
    ):
        """
        Discover animator candidates from video posts.

        This version is deliberately faster than the previous
        implementation.

        Instead of verifying every possible two-word tag,
        we:

            1. collect candidates
            2. remove obvious bad tags
            3. prioritize candidates appearing repeatedly
            4. verify only the strongest candidates
        """

        pages = max(
            4,
            min(
                pages,
                30,
            ),
        )

        candidates = {}

        # ----------------------------------------------------
        # Random pages
        # ----------------------------------------------------

        page_numbers = random.sample(
            range(
                1,
                3001,
            ),
            k=min(
                pages,
                30,
            ),
        )

        # ----------------------------------------------------
        # Collect candidates
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
        # Sort candidates
        # ----------------------------------------------------
        #
        # Repeated appearance is a strong signal.
        # Quality is only a secondary factor.
        # ----------------------------------------------------

        candidate_list = list(
            candidates.values()
        )

        candidate_list.sort(
            key=lambda item: (
                item.get(
                    "post_count",
                    0,
                ),
                item.get(
                    "quality",
                    0,
                ),
            ),
            reverse=True,
        )

        # ----------------------------------------------------
        # Verify only the strongest candidates first.
        #
        # This greatly reduces API requests.
        # ----------------------------------------------------

        verification_limit = min(
            len(candidate_list),
            max(
                40,
                12 * 8,
            ),
        )

        candidate_list = candidate_list[
            :verification_limit
        ]

        verified = []

        # ----------------------------------------------------
        # Verify concurrently in small batches
        # ----------------------------------------------------

        semaphore = asyncio.Semaphore(
            5
        )

        async def verify_candidate(
            candidate
        ):

            async with semaphore:

                tag = candidate.get(
                    "tag"
                )

                if not tag:
                    return None

                try:

                    valid = await self.verify_animator(
                        candidate
                    )

                except Exception as e:

                    print(
                        "Animator verification error:",
                        tag,
                        e,
                    )

                    return None

                if not valid:
                    return None

                return {
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

        # ----------------------------------------------------
        # Batch verification
        # ----------------------------------------------------

        batch_size = 10

        for start in range(
            0,
            len(candidate_list),
            batch_size,
        ):

            batch = candidate_list[
                start:start + batch_size
            ]

            results = await asyncio.gather(
                *[
                    verify_candidate(
                        candidate
                    )
                    for candidate in batch
                ]
            )

            for result in results:

                if result is not None:

                    verified.append(
                        result
                    )

        return verified

    # ========================================================
    # CHOOSE BATTLE ANIMATORS
    # ========================================================

    async def choose_battle_animators(
        self,
        count,
    ):

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # Discovery
        # ----------------------------------------------------
        #
        # 8 pages for a 2-player battle.
        # 16 pages for 4 players.
        # 24 pages for 8 players, etc.
        #
        # Capped to avoid excessive requests.
        # ----------------------------------------------------

        discovery_pages = min(
            24,
            max(
                8,
                count * 3,
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
        # Deduplicate
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

        if len(candidates) < count:

            print(
                f"Only {len(candidates)} verified "
                f"animators available; need {count}."
            )

            return candidates

        # ----------------------------------------------------
        # Calculate selection weight
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
        # Weighted random selection
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

            if await self.verify_animator(
                candidate
            ):

                verified.append(
                    {
                        "name": normalize_name(
                            candidate.get(
                                "tag",
                                candidate.get(
                                    "name",
                                    "",
                                ),
                            )
                        ),

                        "tag": normalize_tag(
                            candidate.get(
                                "tag",
                                candidate.get(
                                    "name",
                                    "",
                                ),
                            )
                        ),

                        "quality": candidate.get(
                            "quality",
                            0,
                        ),
                    }
                )

        # ----------------------------------------------------
        # Fill missing slots
        # ----------------------------------------------------

        if len(verified) < count:

            selected_tags = {
                item["tag"]
                for item in verified
            }

            fallback = [
                candidate
                for candidate in candidates
                if normalize_tag(
                    candidate.get(
                        "tag",
                        "",
                    )
                ) not in selected_tags
            ]

            random.shuffle(
                fallback
            )

            for candidate in fallback:

                if len(verified) >= count:
                    break

                if not await self.verify_animator(
                    candidate
                ):
                    continue

                tag = normalize_tag(
                    candidate.get(
                        "tag",
                        "",
                    )
                )

                if not tag:
                    continue

                if tag in selected_tags:
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

                selected_tags.add(
                    tag
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
        # Continuous
        # ----------------------------------------------------

        if (
            mode == "continuous"
            and previous_clip is not None
        ):

            return previous_clip

        # ----------------------------------------------------
        # Get clips
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
        # New clip
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
        # No unused clip left
        # ----------------------------------------------------

        return previous_clip

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
    difficulty="extreme",
):

    client = SakugabooruClient()

    try:

        return await client.get_random_post(
            difficulty
        )

    finally:

        await client.close()