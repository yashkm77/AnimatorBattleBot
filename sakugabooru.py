import asyncio
import aiohttp
import random
import re
import time


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
    "Referer": BASE_URL + "/",
}

REQUEST_TIMEOUT = 20

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}


# ============================================================
# DISCOVERY SETTINGS
# ============================================================

# Keep this relatively small.
#
# The old code could do:
#
# 100 pages
# × many candidates
# × tag.json requests
#
# which caused the huge delay.
#
# 12 pages is enough to get a decent pool while staying fast.
DISCOVERY_PAGES = 12

POSTS_PER_PAGE = 100

MAX_DISCOVERY_PAGES = 30

# Number of candidates we initially verify.
MAX_CANDIDATES_TO_VERIFY = 80

# We need some spare candidates because some tags will be bad.
MIN_TARGET_POOL_MULTIPLIER = 5


# ============================================================
# KNOWN NON-ANIMATOR TAGS
# ============================================================

IGNORED_TAGS = {
    # --------------------------------------------------------
    # CHARACTER COUNTS
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

    "1other",
    "2others",
    "3others",
    "multiple_girls",
    "multiple_boys",
    "multiple_others",

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

    "solo",
    "duo",
    "group",
    "crowd",

    # --------------------------------------------------------
    # MEDIA
    # --------------------------------------------------------

    "screenshot",
    "official_art",
    "promotional_art",
    "cover",
    "poster",

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

    # --------------------------------------------------------
    # PRODUCTION / NON-PERSON TAGS
    # --------------------------------------------------------

    "production_materials",
    "production_material",
    "key_animation",
    "key_animations",
    "rough_animation",
    "layout",
    "layouts",
    "storyboard",
    "storyboards",
    "animation_drawing",
    "animation_drawing",
    "douga",
    "genga",
    "background_art",
    "background_artist",
    "color_design",
    "color_designs",
    "character_design",
    "character_designs",
    "mechanical_design",
    "mechanical_designs",
    "design",
    "designs",
    "credits",
    "staff",
    "staff_list",
}


# ============================================================
# COMMON NON-PERSON WORDS
# ============================================================

BLOCKED_WORDS = {
    # Anime / release terminology
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
    "chapters",
    "version",
    "versions",
    "arc",
    "arcs",
    "part",
    "parts",
    "series",
    "ova",
    "ovas",
    "ona",
    "onas",
    "tv",
    "film",

    # Production
    "production",
    "material",
    "materials",
    "animation",
    "animated",
    "animator",
    "animators",
    "staff",
    "credit",
    "credits",
    "key",
    "frame",
    "frames",
    "layout",
    "layouts",
    "storyboard",
    "storyboards",
    "director",
    "directors",
    "design",
    "designer",
    "designers",
    "background",
    "camera",
    "effect",
    "effects",
    "mechanical",
    "character",

    # Generic
    "school",
    "uniform",
    "weapon",
    "sword",
    "gun",

    "attack",
    "fight",
    "fighting",
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

    "water",
    "sky",
    "cloud",

    "blood",
    "fire",
    "smoke",
    "explosion",

    # Common non-person nouns
    "world",
    "kingdom",
    "city",
    "village",
    "school",
    "academy",
    "house",
    "building",
    "room",
    "night",
    "day",
    "summer",
    "winter",
    "spring",
    "autumn",
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
    "kuroshitsuji",
    "tiger_mask",
    "production_",
    "pokemon",
)


# ============================================================
# STRONG NON-PERSON SUFFIXES
# ============================================================

BAD_SUFFIXES = (
    "_series",
    "_season",
    "_episode",
    "_movie",
    "_special",
    "_version",
    "_part",
    "_arc",
    "_ova",
    "_ona",
    "_tv",
    "_film",
    "_materials",
    "_material",
    "_animation",
    "_staff",
    "_credits",
    "_opening",
    "_ending",
    "_layout",
    "_layouts",
    "_storyboard",
    "_storyboards",
    "_design",
    "_designs",
    "_background",
    "_effects",
)


# ============================================================
# LIKELY PERSON NAME WORDS
# ============================================================

# These are NOT required, but they help identify obvious
# Japanese / international person-name patterns.

COMMON_GIVEN_NAMES = {
    "yutaka",
    "keiichiro",
    "keiichirou",
    "yuki",
    "yusuke",
    "yuichi",
    "yuichiro",
    "yoshimichi",
    "yoshinori",
    "yoshiyuki",
    "yoshihiro",
    "masashi",
    "masahiro",
    "masayuki",
    "masato",
    "masaki",
    "naoki",
    "naoya",
    "naohiro",
    "takeshi",
    "takuya",
    "takahiro",
    "takashi",
    "kazutoshi",
    "kazuhiko",
    "kazuki",
    "hiroshi",
    "hiroyuki",
    "hiroto",
    "hiromasa",
    "shinya",
    "shinichi",
    "shinji",
    "satoshi",
    "kenichi",
    "kenji",
    "kohei",
    "kohei",
    "koji",
    "koichi",
    "kazuya",
    "katsuro",
    "katsushi",
    "tomohiro",
    "tomoyuki",
    "tomoki",
    "toshiyuki",
    "ryota",
    "ryo",
    "ryuji",
    "ryuichi",
    "akira",
    "atsushi",
    "atsuko",
    "chihiro",
    "fumihide",
    "fumio",
    "genki",
    "hayato",
    "isamu",
    "jun",
    "junichi",
    "kenta",
    "kentaro",
    "makoto",
    "mamoru",
    "megumi",
    "miki",
    "minoru",
    "mitsuo",
    "motoki",
    "noboru",
    "osamu",
    "rei",
    "rikiya",
    "sawako",
    "sho",
    "shota",
    "shouta",
    "taichi",
    "takayuki",
    "tetsuya",
    "tetsuro",
    "tomoaki",
    "toru",
    "wataru",
    "weilin",
    "xiao",
    "chengxi",
    "hao",
    "bahi",
    "kshitij",
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
# NAME-LIKE FILTER
# ============================================================

def looks_like_name(tag: str) -> bool:
    """
    Strong preliminary filter.

    This is intentionally conservative because Sakugabooru
    posts contain lots of anime / production / character tags.

    We do NOT want things such as:

        kuroshitsuji_ii
        tiger_mask_series
        production_materials
        attack_on_titan
    """

    tag = normalize_tag(
        tag
    )

    if not tag:
        return False

    if tag in IGNORED_TAGS:
        return False

    if tag in BLOCKED_WORDS:
        return False

    # Must look like a multi-word name.
    if "_" not in tag:
        return False

    if len(tag) < 5:
        return False

    if len(tag) > 50:
        return False

    # No numbers.
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

    if len(parts) > 5:
        return False

    # Reject absurdly long words.
    if any(
        len(part) > 25
        for part in parts
    ):
        return False

    # Reject blocked words anywhere in the tag.
    for part in parts:

        if part in BLOCKED_WORDS:
            return False

    # Reject obvious anime prefixes.
    for prefix in ANIME_PREFIXES:

        if tag.startswith(prefix):
            return False

    # Reject obvious non-person suffixes.
    for suffix in BAD_SUFFIXES:

        if tag.endswith(suffix):
            return False

    # --------------------------------------------------------
    # Very important:
    #
    # Anime titles often contain "series", "ii", etc.
    # We reject Roman-numeral-like standalone components.
    # --------------------------------------------------------

    roman_pattern = re.compile(
        r"^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)$"
    )

    if any(
        roman_pattern.fullmatch(part)
        for part in parts
    ):
        return False

    # --------------------------------------------------------
    # Reject generic title-like combinations.
    # --------------------------------------------------------

    title_words = {
        "the",
        "new",
        "final",
        "first",
        "second",
        "third",
        "last",
        "great",
        "little",
        "big",
        "dark",
        "red",
        "blue",
        "black",
        "white",
        "gold",
        "silver",
        "zero",
        "one",
        "two",
        "three",
    }

    title_word_count = sum(
        1
        for part in parts
        if part in title_words
    )

    if title_word_count >= 2:
        return False

    return True


# ============================================================
# CLIENT
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

        self.animator_verification_cache = {}

        # ----------------------------------------------------
        # Discovery cache
        # ----------------------------------------------------

        self.discovery_cache = None

        self.discovery_cache_time = 0

        self.discovery_cache_ttl = 300

        # ----------------------------------------------------
        # Request pacing
        # ----------------------------------------------------

        self.last_request_time = 0.0

        self.request_lock = asyncio.Lock()

        self.minimum_request_gap = 0.15

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

            connector = aiohttp.TCPConnector(
                limit=8,
                limit_per_host=4,
                ttl_dns_cache=300,
            )

            self.session = aiohttp.ClientSession(
                headers=HEADERS,
                timeout=timeout,
                connector=connector,
            )

        return self.session

    # ========================================================
    # REQUEST
    # ========================================================

    async def request_json(
        self,
        url: str,
        params=None,
        retries=2,
    ):

        session = await self.get_session()

        for attempt in range(
            retries + 1
        ):

            try:

                # ------------------------------------------------
                # Small global request gap.
                #
                # This prevents hammering Sakugabooru when
                # discovering many pages.
                # ------------------------------------------------

                async with self.request_lock:

                    now = time.monotonic()

                    elapsed = (
                        now
                        - self.last_request_time
                    )

                    if (
                        elapsed
                        < self.minimum_request_gap
                    ):

                        await asyncio.sleep(
                            self.minimum_request_gap
                            - elapsed
                        )

                    self.last_request_time = (
                        time.monotonic()
                    )

                async with session.get(
                    url,
                    params=params,
                ) as response:

                    if response.status == 200:

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

                    # ------------------------------------------------
                    # 503 / 429
                    # ------------------------------------------------

                    if response.status in (
                        429,
                        500,
                        502,
                        503,
                        504,
                    ):

                        if attempt < retries:

                            wait_time = (
                                1.0
                                * (
                                    attempt + 1
                                )
                            )

                            await asyncio.sleep(
                                wait_time
                            )

                            continue

                    print(
                        "Sakugabooru HTTP error:",
                        response.status,
                        url,
                        params,
                    )

                    return None

            except asyncio.TimeoutError:

                if attempt < retries:

                    await asyncio.sleep(
                        1.0
                    )

                    continue

                print(
                    "Sakugabooru request timed out:",
                    url,
                    params,
                )

                return None

            except aiohttp.ClientError as e:

                if attempt < retries:

                    await asyncio.sleep(
                        1.0
                    )

                    continue

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

        # Don't use an enormous random page number.
        #
        # The API may have fewer useful pages and this can
        # produce empty results.
        page = random.randint(
            1,
            MAX_DISCOVERY_PAGES,
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
        Search exact Sakugabooru tag.

        Example:

            yutaka_nakamura
        """

        tag = normalize_tag(
            animator_name
        )

        if not tag:
            return []

        cache_key = (
            tag,
            int(limit),
        )

        if cache_key in self.animator_cache:

            return self.animator_cache[
                cache_key
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
            cache_key
        ] = video_posts

        return video_posts

    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        candidate,
    ):
        """
        Final Sakugabooru-only verification.

        IMPORTANT:

        There is NO tag.json dependency here.

        A candidate is considered usable if:

        1. It passes looks_like_name()
        2. Searching the exact tag returns video posts
        3. The candidate tag itself appears in those posts

        This prevents the previous AttributeError and also
        removes the need for tag.json, which was returning 503.
        """

        if isinstance(
            candidate,
            dict,
        ):

            tag = candidate.get(
                "tag"
            )

        else:

            tag = candidate

        tag = normalize_tag(
            tag
        )

        if not tag:
            return False

        if tag in self.animator_verification_cache:

            return self.animator_verification_cache[
                tag
            ]

        # ----------------------------------------------------
        # Strong name filter
        # ----------------------------------------------------

        if not looks_like_name(
            tag
        ):

            self.animator_verification_cache[
                tag
            ] = False

            return False

        # ----------------------------------------------------
        # Exact tag search
        # ----------------------------------------------------

        posts = await self.get_animator_posts(
            tag,
            limit=100,
        )

        if not posts:

            self.animator_verification_cache[
                tag
            ] = False

            return False

        # ----------------------------------------------------
        # Verify that the tag actually occurs in posts.
        # ----------------------------------------------------

        matching_posts = 0

        for post in posts:

            tags = extract_tags(
                post
            )

            if tag in tags:

                matching_posts += 1

                if matching_posts >= 1:
                    break

        valid = (
            matching_posts > 0
        )

        self.animator_verification_cache[
            tag
        ] = valid

        return valid

    # ========================================================
    # DISCOVER ANIMATORS
    # ========================================================

    async def discover_animators(
        self,
        pages=DISCOVERY_PAGES,
    ):
        """
        Discover candidate animator tags from Sakugabooru
        video posts.

        No tag.json.

        No KFSL.

        No anime database.
        """

        pages = max(
            1,
            min(
                int(pages),
                MAX_DISCOVERY_PAGES,
            ),
        )

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        now = time.monotonic()

        if (
            self.discovery_cache is not None
            and (
                now
                - self.discovery_cache_time
            )
            < self.discovery_cache_ttl
            and len(self.discovery_cache) >= 20
        ):

            return [
                dict(candidate)
                for candidate in self.discovery_cache
            ]

        candidates = {}

        # ----------------------------------------------------
        # Page order
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
        # Fetch pages concurrently.
        #
        # Only a few at once so we don't hammer the site.
        # ----------------------------------------------------

        semaphore = asyncio.Semaphore(
            4
        )

        async def fetch_page(
            page,
        ):

            async with semaphore:

                return await self.get_posts(
                    page=page,
                    limit=POSTS_PER_PAGE,
                )

        results = await asyncio.gather(
            *[
                fetch_page(page)
                for page in page_numbers
            ],
            return_exceptions=True,
        )

        # ----------------------------------------------------
        # Process posts
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

                    except (
                        TypeError,
                        ValueError,
                    ):

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
        # Convert to list
        # ----------------------------------------------------

        candidate_list = list(
            candidates.values()
        )

        # ----------------------------------------------------
        # Score candidates
        #
        # We want people with:
        #
        # - multiple video posts
        # - decent score
        #
        # but still random enough for tournaments.
        # ----------------------------------------------------

        for candidate in candidate_list:

            quality = float(
                candidate.get(
                    "quality",
                    0,
                )
            )

            post_count = int(
                candidate.get(
                    "post_count",
                    0,
                )
            )

            # Multiple clips are very useful for battle.
            clip_score = min(
                post_count,
                20,
            ) * 3.0

            quality_score = min(
                max(
                    quality,
                    0,
                ),
                100,
            )

            candidate[
                "_score"
            ] = (
                clip_score
                + quality_score
            )

        # ----------------------------------------------------
        # Sort mostly by usability.
        # ----------------------------------------------------

        candidate_list.sort(
            key=lambda item: item.get(
                "_score",
                0,
            ),
            reverse=True,
        )

        # ----------------------------------------------------
        # Shuffle groups so selection isn't always identical.
        # ----------------------------------------------------

        top_pool = candidate_list[
            :max(
                20,
                min(
                    200,
                    len(candidate_list),
                ),
            )
        ]

        random.shuffle(
            top_pool
        )

        # Put remaining candidates after top pool.
        remaining = [
            candidate
            for candidate in candidate_list
            if candidate not in top_pool
        ]

        candidate_list = (
            top_pool
            + remaining
        )

        # ----------------------------------------------------
        # Verify candidates.
        #
        # No tag.json.
        # ----------------------------------------------------

        verified = []

        verify_limit = min(
            len(candidate_list),
            MAX_CANDIDATES_TO_VERIFY,
        )

        for candidate in candidate_list[
            :verify_limit
        ]:

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
                    "Animator verification error:",
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

                    "post_count": candidate.get(
                        "post_count",
                        0,
                    ),
                }
            )

        # ----------------------------------------------------
        # Cache
        # ----------------------------------------------------

        self.discovery_cache = [
            dict(candidate)
            for candidate in verified
        ]

        self.discovery_cache_time = (
            time.monotonic()
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

        Sakugabooru only.

        No KFSL.

        No tag.json.

        No external anime database.
        """

        if count < 2:

            raise ValueError(
                "Battle requires at least 2 animators."
            )

        # ----------------------------------------------------
        # Discovery amount
        # ----------------------------------------------------

        required_pool = max(
            20,
            count * MIN_TARGET_POOL_MULTIPLIER,
        )

        discovery_pages = max(
            6,
            min(
                DISCOVERY_PAGES
                + (count // 8) * 2,
                MAX_DISCOVERY_PAGES,
            ),
        )

        candidates = await self.discover_animators(
            pages=discovery_pages
        )

        # ----------------------------------------------------
        # If not enough, one additional discovery pass.
        # ----------------------------------------------------

        if len(candidates) < required_pool:

            extra_pages = min(
                MAX_DISCOVERY_PAGES,
                discovery_pages + 8,
            )

            more = await self.discover_animators(
                pages=extra_pages
            )

            if len(more) > len(candidates):

                candidates = more

        if not candidates:

            print(
                "Sakugabooru returned no usable "
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

            if not looks_like_name(
                tag
            ):
                continue

            unique[tag] = candidate

        candidates = list(
            unique.values()
        )

        if len(candidates) < count:

            print(
                "Not enough usable animator candidates:",
                len(candidates),
                "needed:",
                count,
            )

            return []

        # ----------------------------------------------------
        # RANDOM WEIGHT
        # ----------------------------------------------------

        for candidate in candidates:

            try:

                quality = float(
                    candidate.get(
                        "quality",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                quality = 0.0

            try:

                post_count = int(
                    candidate.get(
                        "post_count",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                post_count = 0

            # Moderate weighting.
            #
            # Don't make the highest-score animator appear
            # every time.
            quality_part = min(
                max(
                    quality,
                    0,
                ),
                50,
            )

            clip_part = min(
                post_count,
                15,
            ) * 2

            candidate[
                "_weight"
            ] = max(
                1.0,
                10.0
                + quality_part
                + clip_part,
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

            if len(verified) >= count:
                break

            tag = normalize_tag(
                candidate.get(
                    "tag",
                    "",
                )
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

                    "post_count": candidate.get(
                        "post_count",
                        0,
                    ),
                }
            )

        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------

        if len(verified) < count:

            selected_tags = {
                item.get(
                    "tag"
                )
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

                tag = normalize_tag(
                    candidate.get(
                        "tag",
                        "",
                    )
                )

                if not tag:
                    continue

                try:

                    valid = await self.verify_animator(
                        candidate
                    )

                except Exception:

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

                        "post_count": candidate.get(
                            "post_count",
                            0,
                        ),
                    }
                )

        # ----------------------------------------------------
        # Final duplicate protection
        # ----------------------------------------------------

        final = []

        seen = set()

        for candidate in verified:

            tag = normalize_tag(
                candidate.get(
                    "tag",
                    "",
                )
            )

            if not tag:
                continue

            if tag in seen:
                continue

            seen.add(
                tag
            )

            final.append(
                candidate
            )

            if len(final) >= count:
                break

        return final

    # ========================================================
    # BATTLE CLIP
    # ========================================================

    async def get_battle_clip(
        self,
        animator_name,
        mode="random",
    ):
        """
        Return a unique Sakugabooru video clip.

        random:
            New clip every time if possible.

        continuous:
            Reuse the animator's previous clip.
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
        # Find unused clip
        # ----------------------------------------------------

        for post in posts:

            if not is_video_post(
                post
            ):
                continue

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
        # If every clip was already used:
        #
        # For random mode, allow reuse of a previous clip
        # rather than failing the entire match.
        # ----------------------------------------------------

        return previous_clip

    # ========================================================
    # FIND ANIMATOR
    # ========================================================

    async def find_animator(
        self,
        tags,
    ):
        """
        Find a usable animator from post tags.

        Sakugabooru only.
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

            if not await self.verify_animator(
                {
                    "tag": tag
                }
            ):
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

        Tournament selection does not use anime tags.
        """

        return None

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

        self.animator_verification_cache.clear()

        self.discovery_cache = None

        self.discovery_cache_time = 0

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