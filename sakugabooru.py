import aiohttp
import asyncio
import json
import os
import random


BASE_URL = "https://www.sakugabooru.com"

# KFSL animator index
ANIMATOR_INDEX_FILE = "animator_index.json"

# Cache verified Sakugabooru animators
POOL_CACHE_FILE = "verified_animators.json"

# Pages checked when searching an animator
VERIFY_PAGES = 5

# Deeper search when necessary
DEEP_SEARCH_PAGES = 15

POSTS_PER_PAGE = 100

REQUEST_CONCURRENCY = 5


class SakugabooruClient:

    def __init__(self):

        self.used_clips = set()

        # Continuous mode keeps one clip per animator.
        self.animator_clips = {}

        self.verified_animators = {}

        # Cache anime tag lookups.
        self.tag_categories = {}

        self._load_cache()

        self.semaphore = asyncio.Semaphore(
            REQUEST_CONCURRENCY
        )

    # ========================================================
    # HTTP HEADERS
    # ========================================================

    @staticmethod
    def get_headers():

        return {
            "User-Agent":
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X) "
                "AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) "
                "Version/26.0 Safari/605.1.15"
        }

    # ========================================================
    # CACHE
    # ========================================================

    def _load_cache(self):

        if not os.path.exists(POOL_CACHE_FILE):

            self.verified_animators = {}

            return

        try:

            with open(
                POOL_CACHE_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

            if isinstance(data, dict):
                self.verified_animators = data
            else:
                self.verified_animators = {}

        except Exception as e:

            print(
                f"Could not load Sakugabooru cache: {e}"
            )

            self.verified_animators = {}

    def _save_cache(self):

        try:

            temp_file = POOL_CACHE_FILE + ".tmp"

            with open(
                temp_file,
                "w",
                encoding="utf-8",
            ) as f:

                json.dump(
                    self.verified_animators,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            os.replace(
                temp_file,
                POOL_CACHE_FILE,
            )

        except Exception as e:

            print(
                f"Could not save Sakugabooru cache: {e}"
            )

    # ========================================================
    # LOAD ANIMATOR INDEX
    # ========================================================

    def load_animator_index(self):

        if not os.path.exists(ANIMATOR_INDEX_FILE):

            print(
                f"❌ {ANIMATOR_INDEX_FILE} not found."
            )

            return []

        try:

            with open(
                ANIMATOR_INDEX_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

        except Exception as e:

            print(
                f"❌ Could not load animator index: {e}"
            )

            return []

        people = data.get(
            "people",
            {}
        )

        names = []

        seen = set()

        for person in people.values():

            if not isinstance(person, dict):
                continue

            person_names = person.get(
                "names",
                []
            )

            if not isinstance(
                person_names,
                list,
            ):
                continue

            for name in person_names:

                if not isinstance(
                    name,
                    str,
                ):
                    continue

                name = name.strip()

                if not name:
                    continue

                if not any(
                    char.isascii()
                    and char.isalpha()
                    for char in name
                ):
                    continue

                key = name.lower()

                if key in seen:
                    continue

                seen.add(key)

                names.append(name)

                break

        return names

    # ========================================================
    # NAME → TAG
    # ========================================================

    def name_to_tag(
        self,
        animator_name: str,
    ):

        return (
            animator_name
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

    # ========================================================
    # SAFE INTEGER
    # ========================================================

    @staticmethod
    def safe_int(value):

        try:
            return int(value or 0)
        except Exception:
            return 0

    # ========================================================
    # POST QUALITY
    # ========================================================

    @classmethod
    def post_quality(cls, post):

        score = cls.safe_int(
            post.get("score")
        )

        favorites = cls.safe_int(
            post.get("fav_count")
        )

        up_score = cls.safe_int(
            post.get("up_score")
        )

        # ----------------------------------------------------
        # Favourites are intentionally NOT capped at 100.
        #
        # A post with 2,000 favourites should have a much
        # stronger chance than one with 50.
        # ----------------------------------------------------

        quality = (
            max(score, 0) * 4
            + max(up_score, 0) * 2
            + max(favorites, 0) * 1.5
        )

        return quality

    # ========================================================
    # SEARCH ANIMATOR
    # ========================================================

    async def search_animator(
        self,
        session,
        animator_name: str,
        max_pages: int = VERIFY_PAGES,
    ):

        tag = self.name_to_tag(
            animator_name
        )

        clips = []

        seen_ids = set()

        async with self.semaphore:

            for page in range(
                1,
                max_pages + 1,
            ):

                url = (
                    f"{BASE_URL}/post.json"
                    f"?tags={tag}"
                    f"&page={page}"
                    f"&limit={POSTS_PER_PAGE}"
                )

                try:

                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(
                            total=20
                        ),
                    ) as resp:

                        if resp.status != 200:

                            print(
                                f"⚠️ Sakugabooru returned "
                                f"HTTP {resp.status} "
                                f"for {animator_name}"
                            )

                            continue

                        posts = await resp.json(
                            content_type=None
                        )

                except asyncio.TimeoutError:

                    print(
                        f"⏱️ Sakugabooru timeout "
                        f"for {animator_name}"
                    )

                    continue

                except Exception as e:

                    print(
                        f"Sakugabooru search error "
                        f"for {animator_name}: {e}"
                    )

                    continue

                if not isinstance(
                    posts,
                    list,
                ):
                    continue

                if not posts:
                    break

                for post in posts:

                    ext = str(
                        post.get(
                            "file_ext",
                            ""
                        )
                    ).lower()

                    if ext not in (
                        "mp4",
                        "webm",
                    ):
                        continue

                    file_url = post.get(
                        "file_url"
                    )

                    if not file_url:
                        continue

                    post_id = post.get(
                        "id"
                    )

                    if post_id is None:
                        continue

                    if post_id in seen_ids:
                        continue

                    seen_ids.add(
                        post_id
                    )

                    tags = post.get(
                        "tags",
                        ""
                    )

                    if isinstance(
                        tags,
                        str,
                    ):

                        tag_list = tags.split()

                    elif isinstance(
                        tags,
                        list,
                    ):

                        tag_list = tags

                    else:

                        tag_list = []

                    quality = self.post_quality(
                        post
                    )

                    clips.append({
                        "id": post_id,

                        "url": file_url,

                        "preview_url":
                            post.get(
                                "preview_url"
                            ),

                        "animator":
                            animator_name,

                        "animator_tag":
                            tag,

                        "score":
                            self.safe_int(
                                post.get("score")
                            ),

                        "fav_count":
                            self.safe_int(
                                post.get("fav_count")
                            ),

                        "up_score":
                            self.safe_int(
                                post.get("up_score")
                            ),

                        "quality":
                            quality,

                        "tags":
                            tag_list,

                        # Keep the complete original post
                        # for later metadata extraction.
                        "post":
                            post,
                    })

        return tag, clips

    # ========================================================
    # FIND ANIME FROM POST TAGS
    # ========================================================

    async def find_anime_from_clip(
        self,
        clip,
    ):

        """
        Try to identify the anime/copyright tag.

        This is ONLY used after voting, so even if metadata
        detection isn't perfect it cannot spoil the matchup.
        """

        tags = clip.get(
            "tags",
            []
        )

        if not tags:
            post = clip.get(
                "post",
                {}
            )

            raw_tags = post.get(
                "tags",
                ""
            )

            if isinstance(
                raw_tags,
                str,
            ):
                tags = raw_tags.split()

        if not tags:
            return None

        animator_tag = clip.get(
            "animator_tag",
            ""
        ).lower()

        # ----------------------------------------------------
        # First try Sakugabooru's tag categories.
        # Category 3 is the copyright/anime category on the
        # Danbooru-style API used by Sakugabooru.
        # ----------------------------------------------------

        candidates = []

        for tag in tags:

            tag = str(tag).strip()

            if not tag:
                continue

            if tag.lower() == animator_tag:
                continue

            if tag not in candidates:
                candidates.append(tag)

        if not candidates:
            return None

        headers = self.get_headers()

        async with aiohttp.ClientSession(
            headers=headers
        ) as session:

            for tag in candidates:

                cache_key = tag.lower()

                if cache_key in self.tag_categories:

                    category = self.tag_categories[
                        cache_key
                    ]

                    if category == 3:
                        return self.pretty_tag(tag)

                    continue

                url = (
                    f"{BASE_URL}/tag.json"
                    f"?name={tag}"
                )

                try:

                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(
                            total=10
                        ),
                    ) as resp:

                        if resp.status != 200:
                            continue

                        data = await resp.json(
                            content_type=None
                        )

                except Exception:
                    continue

                category = None

                if isinstance(data, list) and data:

                    item = data[0]

                    if isinstance(item, dict):

                        category = self.safe_int(
                            item.get(
                                "category"
                            )
                        )

                elif isinstance(data, dict):

                    category = self.safe_int(
                        data.get(
                            "category"
                        )
                    )

                self.tag_categories[
                    cache_key
                ] = category

                if category == 3:

                    return self.pretty_tag(
                        tag
                    )

        # ----------------------------------------------------
        # Fallback:
        #
        # If the tag endpoint isn't available, select the
        # most likely copyright/anime-looking tag.
        #
        # This happens ONLY after the result.
        # ----------------------------------------------------

        blocked = {
            animator_tag,

            "video",
            "animated",
            "animation",
            "anime",
            "sakuga",
            "music",
            "sound",
            "audio",

            "solo",
            "group",
            "male",
            "female",
            "background",
            "character",
            "school",
            "city",
            "night",
            "day",
        }

        possible = []

        for tag in candidates:

            lower = tag.lower()

            if lower in blocked:
                continue

            if lower.endswith(
                (
                    "_san",
                    "_kun",
                    "_chan",
                )
            ):
                continue

            if lower.startswith(
                (
                    "artist_",
                    "character_",
                )
            ):
                continue

            possible.append(tag)

        if possible:

            # Copyright/anime tags are usually more useful
            # than generic tags. Prefer tags containing common
            # franchise naming patterns, while retaining a
            # deterministic fallback.
            preferred = []

            for tag in possible:

                lower = tag.lower()

                if any(
                    word in lower
                    for word in (
                        "season",
                        "movie",
                        "film",
                        "arc",
                        "series",
                    )
                ):
                    preferred.append(tag)

            if preferred:

                return self.pretty_tag(
                    preferred[0]
                )

            return self.pretty_tag(
                possible[0]
            )

        return None

    # ========================================================
    # PRETTY TAG
    # ========================================================

    @staticmethod
    def pretty_tag(tag):

        if not tag:
            return None

        return (
            str(tag)
            .replace("_", " ")
            .strip()
            .title()
        )

    # ========================================================
    # FIND CLIP
    # ========================================================

    async def find_clip_for_animator(
        self,
        animator_name: str,
    ):

        if not animator_name:
            return None

        animator_name = animator_name.strip()

        if not animator_name:
            return None

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            _, clips = await self.search_animator(
                session,
                animator_name,
                max_pages=VERIFY_PAGES,
            )

            if not clips:

                _, clips = await self.search_animator(
                    session,
                    animator_name,
                    max_pages=DEEP_SEARCH_PAGES,
                )

        if not clips:
            return None

        weights = []

        for clip in clips:

            quality = float(
                clip.get(
                    "quality",
                    0,
                )
            )

            weights.append(
                max(
                    1,
                    quality + 10,
                )
            )

        return random.choices(
            clips,
            weights=weights,
            k=1,
        )[0]

    # ========================================================
    # VERIFY ANIMATOR
    # ========================================================

    async def verify_animator(
        self,
        animator_name: str,
        session=None,
        force=False,
    ):

        key = animator_name.strip().lower()

        cached = self.verified_animators.get(
            key
        )

        if (
            cached is not None
            and not force
        ):
            return cached

        own_session = False

        if session is None:

            session = aiohttp.ClientSession(
                headers=self.get_headers()
            )

            own_session = True

        try:

            tag, clips = await self.search_animator(
                session,
                animator_name,
                max_pages=VERIFY_PAGES,
            )

            if not clips:

                # One deeper attempt.
                tag, clips = await self.search_animator(
                    session,
                    animator_name,
                    max_pages=DEEP_SEARCH_PAGES,
                )

            if not clips:

                result = {
                    "name":
                        animator_name,

                    "tag":
                        tag,

                    "has_clips":
                        False,

                    "clip_count":
                        0,

                    "best_quality":
                        0,

                    "total_quality":
                        0,

                    "quality":
                        0,
                }

            else:

                qualities = [
                    float(
                        clip.get(
                            "quality",
                            0,
                        )
                    )
                    for clip in clips
                ]

                best_quality = max(
                    qualities
                )

                total_quality = sum(
                    qualities
                )

                favorites = sum(
                    self.safe_int(
                        clip.get(
                            "fav_count"
                        )
                    )
                    for clip in clips
                )

                # ------------------------------------------------
                # Participant quality.
                #
                # Favourites have a strong influence, but clip
                # count and score also matter.
                # ------------------------------------------------

                battle_quality = (
                    best_quality * 0.50
                    + total_quality * 0.10
                    + min(
                        len(clips),
                        100,
                    ) * 3
                    + min(
                        favorites,
                        5000,
                    ) * 0.40
                )

                result = {
                    "name":
                        animator_name,

                    "tag":
                        tag,

                    "has_clips":
                        True,

                    "clip_count":
                        len(clips),

                    "best_quality":
                        best_quality,

                    "total_quality":
                        total_quality,

                    "total_favorites":
                        favorites,

                    "quality":
                        battle_quality,
                }

            self.verified_animators[
                key
            ] = result

            self._save_cache()

            return result

        finally:

            if own_session:
                await session.close()

    # ========================================================
    # VERIFY MANY
    # ========================================================

    async def verify_many(
        self,
        animator_names: list[str],
        force=False,
    ):

        unique = []

        seen = set()

        for name in animator_names:

            if not isinstance(
                name,
                str,
            ):
                continue

            name = name.strip()

            if not name:
                continue

            key = name.lower()

            if key in seen:
                continue

            seen.add(key)

            unique.append(name)

        if not unique:
            return []

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            tasks = [
                self.verify_animator(
                    name,
                    session=session,
                    force=force,
                )
                for name in unique
            ]

            results = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        verified = []

        for result in results:

            if isinstance(
                result,
                Exception,
            ):
                continue

            if result.get(
                "has_clips"
            ):
                verified.append(
                    result
                )

        return verified

    # ========================================================
    # BUILD BATTLE POOL
    # ========================================================

    async def build_battle_pool(
        self,
        force=False,
    ):

        names = self.load_animator_index()

        if not names:
            return []

        print(
            f"🔎 Checking {len(names):,} animators "
            f"against Sakugabooru..."
        )

        verified = await self.verify_many(
            names,
            force=force,
        )

        if not verified:

            print(
                "❌ No verified animators found."
            )

            return []

        verified.sort(
            key=lambda x: float(
                x.get(
                    "quality",
                    0,
                )
            ),
            reverse=True,
        )

        print(
            f"✅ Found {len(verified):,} "
            f"animators with video clips."
        )

        return verified

    # ========================================================
    # CHOOSE BATTLE ANIMATORS
    # ========================================================

    async def choose_battle_animators(
        self,
        count: int,
    ):

        pool = await self.build_battle_pool()

        if len(pool) < count:
            return []

        candidates = pool.copy()

        selected = []

        for _ in range(count):

            if not candidates:
                break

            weights = []

            for animator in candidates:

                quality = float(
                    animator.get(
                        "quality",
                        0,
                    )
                )

                # Stronger animators get higher probability,
                # but the entire pool remains available.
                weight = max(
                    1,
                    quality ** 0.65,
                )

                weights.append(
                    weight
                )

            chosen = random.choices(
                candidates,
                weights=weights,
                k=1,
            )[0]

            selected.append(
                chosen
            )

            candidates.remove(
                chosen
            )

        return selected

    # ========================================================
    # GET CLIPS
    # ========================================================

    async def get_clips(
        self,
        animator_input: str,
        count: int = 10,
    ):

        if not animator_input:

            return (
                self.name_to_tag(""),
                [],
            )

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            _, clips = await self.search_animator(
                session,
                animator_input,
                max_pages=VERIFY_PAGES,
            )

        available = [
            clip
            for clip in clips
            if clip["id"]
            not in self.used_clips
        ]

        random.shuffle(
            available
        )

        return (
            self.name_to_tag(
                animator_input
            ),
            available[:count],
        )

    # ========================================================
    # RANDOM CLIP
    # ========================================================

    async def get_random_clip(
        self,
        animator_name: str,
    ):

        if not animator_name:
            return None

        _, clips = await self.get_clips(
            animator_name,
            count=50,
        )

        available = [
            clip
            for clip in clips
            if clip["id"]
            not in self.used_clips
        ]

        # ----------------------------------------------------
        # Deeper search if required.
        # ----------------------------------------------------

        if not available:

            async with aiohttp.ClientSession(
                headers=self.get_headers()
            ) as session:

                _, clips = await self.search_animator(
                    session,
                    animator_name,
                    max_pages=DEEP_SEARCH_PAGES,
                )

            available = [
                clip
                for clip in clips
                if clip["id"]
                not in self.used_clips
            ]

        if not available:
            return None

        # ----------------------------------------------------
        # QUALITY + FAVOURITE WEIGHTING
        # ----------------------------------------------------

        weights = []

        for clip in available:

            score = self.safe_int(
                clip.get("score")
            )

            favorites = self.safe_int(
                clip.get("fav_count")
            )

            quality = float(
                clip.get(
                    "quality",
                    0,
                )
            )

            # Logarithmic favourite weighting prevents one
            # enormous post from completely dominating.
            favorite_bonus = (
                1
                + (favorites + 1) ** 0.75
            )

            score_bonus = (
                1
                + max(score, 0) ** 0.80
            )

            quality_bonus = (
                1
                + max(quality, 0) ** 0.65
            )

            weight = (
                favorite_bonus
                * score_bonus
                * quality_bonus
            )

            weights.append(
                max(
                    1,
                    weight,
                )
            )

        clip = random.choices(
            available,
            weights=weights,
            k=1,
        )[0]

        self.used_clips.add(
            clip["id"]
        )

        return clip

    # ========================================================
    # CONTINUOUS CLIP
    # ========================================================

    async def get_continuous_clip(
        self,
        animator_name: str,
    ):

        key = animator_name.strip().lower()

        if key in self.animator_clips:

            return self.animator_clips[
                key
            ]

        clip = await self.get_random_clip(
            animator_name
        )

        if clip is None:
            return None

        self.animator_clips[
            key
        ] = clip

        return clip

    # ========================================================
    # BATTLE CLIP
    # ========================================================

    async def get_battle_clip(
        self,
        animator_name: str,
        mode: str,
    ):

        if mode == "continuous":

            return await self.get_continuous_clip(
                animator_name
            )

        return await self.get_random_clip(
            animator_name
        )

    # ========================================================
    # RESET
    # ========================================================

    def reset(self):

        self.used_clips.clear()

        self.animator_clips.clear()

        self.tag_categories.clear()