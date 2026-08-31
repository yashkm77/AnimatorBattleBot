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

# Danbooru/Sakugabooru artist category
ARTIST_CATEGORY = 1


# ============================================================
# OBVIOUS NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # People / character counts
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

    # Body / pose
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

    # Action
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

    "landscape",
    "scenery",
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

    tags = post.get("tags")

    if not tags:
        tags = post.get(
            "tag_string",
            "",
        )

    if isinstance(tags, list):

        result = []

        for tag in tags:

            normalized = normalize_tag(tag)

            if normalized:
                result.append(normalized)

        return result

    if not isinstance(tags, str):
        return []

    result = []

    for tag in tags.split():

        normalized = normalize_tag(tag)

        if normalized:
            result.append(normalized)

    return result


# ============================================================
# NAME-LIKE FILTER
# ============================================================

def looks_like_name(tag: str) -> bool:
    """
    Preliminary filter.

    This does NOT prove the tag is an animator.
    Actual verification happens separately.
    """

    tag = normalize_tag(tag)

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    # Names generally have multiple words.
    if "_" not in tag:
        return False

    if len(tag) < 5:
        return False

    if len(tag) > 60:
        return False

    # No numbers.
    if re.search(r"\d", tag):
        return False

    # Latin lowercase + underscores only.
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

    # Reject absurdly long words.
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
    # REQUEST JSON
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
    # GET POSTS
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
    # GET TAG INFO
    # ========================================================

    async def get_tag_info(
        self,
        tag: str,
    ):
        """
        Get Sakugabooru tag information.

        Returns:
            category number
            or None if the tag endpoint cannot be used.
        """

        tag = normalize_tag(tag)

        if not tag:
            return None

        if tag in self.tag_category_cache:

            return self.tag_category_cache[tag]

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

        self.tag_category_cache[tag] = category

        return category


    # ========================================================
    # ANIMATOR POSTS
    # ========================================================

    async def get_animator_posts(
        self,
        animator_name,
        limit=100,
    ):
        """
        Search Sakugabooru for an exact tag.

        Example:

            Yutaka Nakamura
                    ↓
            yutaka_nakamura
                    ↓
            /post.json?tags=yutaka_nakamura
        """

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
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate,
    ):
        """
        Final animator verification.

        A candidate is accepted when:

        1. It looks like a person-name tag.
        2. Sakugabooru has usable video posts for the tag.

        If the tag API works and explicitly says category 1,
        that is also accepted as artist confirmation.

        IMPORTANT:
        KFSL is not used.
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

        else:

            tag = normalize_tag(
                candidate.get(
                    "tag",
                    candidate.get(
                        "name",
                        "",
                    ),
                )
            )

        if not tag:
            return False

        # Basic filter.
        if not looks_like_name(tag):
            return False

        # ----------------------------------------------------
        # Get actual video posts.
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:

            return False

        # ----------------------------------------------------
        # Artist category.
        # ----------------------------------------------------
        #
        # If the tag API explicitly identifies the tag as an
        # artist, that's strong confirmation.
        #
        # If the tag API is unavailable, the usable-video
        # result above remains our fallback.
        # ----------------------------------------------------

        category = await self.get_tag_info(tag)

        if category == ARTIST_CATEGORY:

            self.artist_tag_cache[tag] = True

            return True

        if category is not None:

            # Sakugabooru explicitly says it is another
            # category, so don't call it an animator.
            self.artist_tag_cache[tag] = False

            return False

        # ----------------------------------------------------
        # Tag API unavailable.
        #
        # Since we already found actual Sakugabooru video
        # posts for this exact name-like tag, accept it.
        # ----------------------------------------------------

        self.artist_tag_cache[tag] = True

        return True


    # ========================================================
    # IS ARTIST TAG
    # ========================================================

    async def is_artist_tag(
        self,
        tag: str,
    ) -> bool:

        tag = normalize_tag(tag)

        if not tag:
            return False

        if tag in self.artist_tag_cache:

            return self.artist_tag_cache[tag]

        if not looks_like_name(tag):

            self.artist_tag_cache[tag] = False

            return False

        # ----------------------------------------------------
        # Get exact posts first.
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:

            self.artist_tag_cache[tag] = False

            return False

        # ----------------------------------------------------
        # Check category.
        # ----------------------------------------------------

        category = await self.get_tag_info(tag)

        if category is not None:

            result = (
                category == ARTIST_CATEGORY
            )

        else:

            # Tag API unavailable.
            # Actual usable videos become fallback.
            result = True

        self.artist_tag_cache[tag] = result

        return result


    # ========================================================
    # FIND ANIMATOR
    # ========================================================

    async def find_animator(
        self,
        tags,
    ):
        """
        Find an animator from tags attached to a post.
        """

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

            try:

                valid = await self.verify_animator(
                    {
                        "tag": tag,
                    }
                )

            except Exception as e:

                print(
                    "Animator verification error:",
                    tag,
                    e,
                )

                valid = False

            if not valid:
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
        """
        Compatibility function.

        Tournament selection does not use anime tags.
        """

        return None


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
    # DISCOVER ANIMATORS
    # ========================================================

    async def discover_animators(
        self,
        pages=30,
    ):
        """
        Discover candidate artist tags from actual
        Sakugabooru video posts.
        """

        pages = max(
            1,
            min(
                pages,
                100,
            ),
        )

        candidates = {}

        page_numbers = list(
            range(
                1,
                pages + 1,
            )
        )

        random.shuffle(page_numbers)

        # ----------------------------------------------------
        # DISCOVER TAGS
        # ----------------------------------------------------

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
        # VERIFY
        # ----------------------------------------------------

        verified = []

        for candidate in candidate_list:

            tag = candidate.get("tag")

            if not tag:
                continue

            try:

                valid = await self.verify_animator(
                    candidate
                )

            except Exception as e:

                print(
                    "Artist verification error:",
                    tag,
                    e,
                )

                valid = False

            if not valid:
                continue

            verified.append(
                {
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
        Select random animators for a tournament.

        Source:
            Sakugabooru only.

        KFSL:
            NOT USED.

        Anime database:
            NOT USED.
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # DISCOVERY
        # ----------------------------------------------------

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
        # WEIGHTS
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
        # RANDOM SELECTION
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

            tag = candidate.get("tag")

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

            selected_tags = {
                item["tag"]
                for item in verified
            }

            fallback_candidates = [
                candidate
                for candidate in candidates
                if candidate.get("tag")
                not in selected_tags
            ]

            random.shuffle(
                fallback_candidates
            )

            for candidate in fallback_candidates:

                if len(verified) >= count:
                    break

                tag = candidate.get("tag")

                if not tag:
                    continue

                try:

                    valid = await self.verify_animator(
                        candidate
                    )

                except Exception as e:

                    print(
                        "Fallback animator verification error:",
                        tag,
                        e,
                    )

                    valid = False

                if not valid:
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
        # FINAL RANDOMIZATION
        # ----------------------------------------------------

        random.shuffle(verified)

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
        # CONTINUOUS
        # ----------------------------------------------------

        if (
            mode == "continuous"
            and previous_clip is not None
        ):

            return previous_clip

        # ----------------------------------------------------
        # POSTS
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
        # NEW CLIP
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
        # NO NEW CLIP
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