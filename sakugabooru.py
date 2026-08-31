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

MAX_POST_PAGES = 3000

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}

# Sakugabooru / Danbooru artist category
ARTIST_CATEGORY = 1


# ============================================================
# OBVIOUS NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # people / counts
    "1girl", "1boy",
    "2girls", "2boys",
    "3girls", "3boys",
    "4girls", "4boys",
    "5girls", "5boys",
    "6girls", "6boys",
    "7girls", "7boys",
    "8girls", "8boys",

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
# COMMON NON-ANIMATOR WORDS
# ============================================================

BLOCKED_WORDS = {
    "season",
    "episode",
    "episodes",
    "opening",
    "ending",
    "movie",
    "special",
    "chapter",
    "version",
    "arc",
    "part",

    "character",
    "characters",

    "background",
    "camera",
    "effect",
    "effects",

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

    "landscape",
    "scenery",

    "production",
    "material",
    "materials",

    "series",
    "project",
    "studio",

    "character",
    "characters",

    "layout",
    "design",
    "designs",

    "key",
    "frame",
    "frames",

    "animation",
    "animator",

    "credits",
    "credit",
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
# EXTRA COPYRIGHT / SHOW-LIKE PATTERNS
# ============================================================

SHOW_LIKE_WORDS = {
    "ii",
    "iii",
    "iv",
    "v",
    "zero",
    "alpha",
    "beta",
    "remake",
    "rebuild",
    "brothers",
    "battle",
    "chronicle",
    "chronicles",
    "story",
    "stories",
    "adventures",
    "adventure",
    "world",
    "worlds",
    "online",
    "season",
    "series",
    "film",
    "films",
}


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

    if not isinstance(post, dict):
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


def post_url(post: dict) -> str | None:

    if not isinstance(post, dict):
        return None

    return post.get(
        "file_url"
    )


def extract_tags(post: dict) -> list[str]:

    if not isinstance(post, dict):
        return []

    tags = post.get(
        "tags"
    )

    if not tags:
        tags = post.get(
            "tag_string",
            "",
        )

    if isinstance(tags, list):

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

    if not isinstance(tags, str):
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

def looks_like_name(tag: str) -> bool:

    tag = normalize_tag(tag)

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

    # obvious non-person words
    for part in parts:

        if part in BLOCKED_WORDS:
            return False

    # obvious anime prefixes
    for prefix in ANIME_PREFIXES:

        if tag.startswith(prefix):
            return False

    # obvious show/franchise wording
    if any(
        part in SHOW_LIKE_WORDS
        for part in parts
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

        """
        Get the exact Sakugabooru tag record.

        Category:
            0 = general
            1 = artist
            3 = copyright
            4 = character
            5 = meta

        We ONLY accept category 1 for tournament
        animator selection.
        """

        tag = normalize_tag(tag)

        if not tag:
            return None

        if tag in self.tag_category_cache:
            return self.tag_category_cache[tag]

        # ----------------------------------------------------
        # Sakugabooru's tag endpoint
        # ----------------------------------------------------

        params = {
            "name": tag,
            "limit": 100,
        }

        data = await self.request_json(
            TAG_API,
            params,
        )

        category = None

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

                # EXACT match only.
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

        elif isinstance(data, dict):

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

        self.tag_category_cache[tag] = category

        return category


    # ========================================================
    # ARTIST TAG CHECK
    # ========================================================

    async def is_artist_tag(
        self,
        tag: str,
    ) -> bool:

        """
        STRICT artist verification.

        IMPORTANT:

        We no longer use the old dangerous fallback:

            "if it has a video, it's an animator"

        That fallback was responsible for things like:

            kuroshitsuji ii
            tiger mask series
            production materials

        being selected.

        A tournament candidate MUST be an artist-category tag.
        """

        tag = normalize_tag(tag)

        if not tag:
            return False

        if tag in self.artist_tag_cache:
            return self.artist_tag_cache[tag]

        if not looks_like_name(tag):

            self.artist_tag_cache[tag] = False

            return False

        category = await self.get_tag_info(
            tag
        )

        # ----------------------------------------------------
        # STRICT RULE
        # ----------------------------------------------------

        result = (
            category == ARTIST_CATEGORY
        )

        self.artist_tag_cache[tag] = result

        return result


    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate,
    ) -> bool:

        """
        Final safety check used by choose_battle_animators().

        This method was missing from the previous version.

        It verifies:

        1. Candidate exists.
        2. Candidate has a valid tag.
        3. Tag is an actual artist-category tag.
        4. Tag has usable video posts.
        """

        if not candidate:
            return False

        if isinstance(
            candidate,
            str,
        ):

            tag = normalize_tag(
                candidate
            )

        elif isinstance(
            candidate,
            dict,
        ):

            tag = normalize_tag(
                candidate.get(
                    "tag",
                    candidate.get(
                        "name",
                        "",
                    ),
                )
            )

        else:

            return False

        if not tag:
            return False

        # ----------------------------------------------------
        # STRICT ARTIST CHECK
        # ----------------------------------------------------

        if not await self.is_artist_tag(
            tag
        ):
            return False

        # ----------------------------------------------------
        # MUST HAVE VIDEO
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:
            return False

        # ----------------------------------------------------
        # Make sure at least one usable URL exists.
        # ----------------------------------------------------

        for post in posts:

            if not is_video_post(post):
                continue

            if post_url(post):
                return True

        return False


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

        random.shuffle(posts)

        for post in posts:

            if not is_video_post(post):
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

        self.animator_cache[tag] = video_posts

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

            if not looks_like_name(tag):
                continue

            candidates.append(tag)

        if not candidates:
            return None

        random.shuffle(candidates)

        for tag in candidates:

            if not await self.is_artist_tag(tag):
                continue

            posts = await self.get_animator_posts(
                tag,
                limit=100,
            )

            if not posts:
                continue

            return {
                "name": normalize_name(tag),
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
        Faster discovery.

        We collect candidate tags from a relatively small
        number of pages, then verify them concurrently.

        Only artist-category tags survive.
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
                MAX_POST_PAGES + 1,
            ),
            pages,
        )

        # ----------------------------------------------------
        # Fetch pages concurrently
        # ----------------------------------------------------

        tasks = [
            self.get_posts(
                page=page,
                limit=100,
            )
            for page in page_numbers
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        # ----------------------------------------------------
        # Collect candidate tags
        # ----------------------------------------------------

        for posts in results:

            if isinstance(
                posts,
                Exception,
            ):
                continue

            if not posts:
                continue

            for post in posts:

                if not is_video_post(post):
                    continue

                tags = extract_tags(post)

                for tag in tags:

                    if not looks_like_name(tag):
                        continue

                    if tag not in candidates:

                        candidates[tag] = {
                            "name": normalize_name(tag),
                            "tag": tag,
                            "quality": 0.0,
                            "post_count": 0,
                        }

                    candidates[tag]["post_count"] += 1

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

        if not candidates:
            return []

        candidate_list = list(
            candidates.values()
        )

        random.shuffle(candidate_list)

        # ----------------------------------------------------
        # Verify artist tags concurrently
        # ----------------------------------------------------

        async def verify_candidate(candidate):

            tag = candidate["tag"]

            try:

                valid = await self.is_artist_tag(
                    tag
                )

                if not valid:
                    return None

                posts = await self.get_animator_posts(
                    tag,
                    limit=100,
                )

                if not posts:
                    return None

                return {
                    "name": normalize_name(tag),
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

            except Exception as e:

                print(
                    "Animator verification error:",
                    tag,
                    e,
                )

                return None

        # Don't send hundreds of requests at once.
        # Check candidates in small batches.
        verified = []

        batch_size = 15

        for index in range(
            0,
            len(candidate_list),
            batch_size,
        ):

            batch = candidate_list[
                index:index + batch_size
            ]

            results = await asyncio.gather(
                *[
                    verify_candidate(candidate)
                    for candidate in batch
                ],
                return_exceptions=True,
            )

            for result in results:

                if isinstance(
                    result,
                    dict,
                ):

                    verified.append(result)

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
            Sakugabooru only.

        Requirements:
            - actual artist-category tag
            - usable video
            - unique animator
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # Discovery
        # ----------------------------------------------------
        #
        # Previously this could scan 100 pages and then
        # verify candidates one by one.
        #
        # This version starts smaller and works upward.
        # ----------------------------------------------------

        discovery_pages = min(
            18,
            max(
                6,
                count * 3,
            ),
        )

        candidates = await self.discover_animators(
            pages=discovery_pages
        )

        # ----------------------------------------------------
        # If not enough, perform another small discovery.
        # ----------------------------------------------------

        if len(candidates) < count:

            extra = await self.discover_animators(
                pages=12
            )

            candidates.extend(extra)

        if not candidates:

            print(
                "Sakugabooru returned no verified "
                "artist-category candidates."
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

        # ----------------------------------------------------
        # Shuffle first
        # ----------------------------------------------------

        random.shuffle(candidates)

        # ----------------------------------------------------
        # Weight
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

            candidate["_weight"] = (
                quality_weight
                + clip_bonus
            )

        # ----------------------------------------------------
        # Select
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

            selected.append(candidate)

            remaining.remove(candidate)

        # ----------------------------------------------------
        # FINAL VERIFICATION
        # ----------------------------------------------------

        verified = []

        for candidate in selected:

            if await self.verify_animator(
                candidate
            ):

                tag = normalize_tag(
                    candidate.get(
                        "tag",
                        "",
                    )
                )

                if not tag:
                    continue

                verified.append(
                    {
                        "name": normalize_name(tag),
                        "tag": tag,
                        "quality": candidate.get(
                            "quality",
                            0,
                        ),
                    }
                )

        # ----------------------------------------------------
        # FILL REMAINING SLOTS
        # ----------------------------------------------------

        if len(verified) < count:

            used_tags = {
                item["tag"]
                for item in verified
            }

            remaining_candidates = [
                candidate
                for candidate in remaining
                if candidate.get(
                    "tag"
                ) not in used_tags
            ]

            random.shuffle(
                remaining_candidates
            )

            for candidate in remaining_candidates:

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

                if tag in used_tags:
                    continue

                verified.append(
                    {
                        "name": normalize_name(tag),
                        "tag": tag,
                        "quality": candidate.get(
                            "quality",
                            0,
                        ),
                    }
                )

                used_tags.add(tag)

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
        # Get posts
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            animator_key,
            limit=100,
        )

        if not posts:

            return previous_clip

        posts = posts.copy()

        random.shuffle(posts)

        used_by_animator = (
            self.animator_clips.get(
                animator_key,
                set(),
            )
        )

        # ----------------------------------------------------
        # Find unused clip
        # ----------------------------------------------------

        for post in posts:

            url = post_url(post)

            if not url:
                continue

            if url in used_by_animator:
                continue

            if url in self.used_clips:
                continue

            clip = {
                "url": url,
                "id": post.get("id"),
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
        # Fallback
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