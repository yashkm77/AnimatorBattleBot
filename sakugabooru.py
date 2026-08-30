import aiohttp
import asyncio
import json
import os
import random


BASE_URL = "https://www.sakugabooru.com"

# Your KFSL animator index
ANIMATOR_INDEX_FILE = "animator_index.json"

# Cache verified Sakugabooru animators
POOL_CACHE_FILE = "verified_animators.json"

# Pages checked when verifying an animator
VERIFY_PAGES = 3

# Posts per Sakugabooru page
POSTS_PER_PAGE = 100

# Maximum simultaneous searches
REQUEST_CONCURRENCY = 5


class SakugabooruClient:

    def __init__(self):

        self.used_clips = set()

        # Used by continuous mode.
        # One clip is kept for each animator during a battle.
        self.animator_clips = {}

        # Cached information about animators that have clips.
        self.verified_animators = {}

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
    # LOAD ALL ANIMATORS FROM KFSL INDEX
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

            person_names = person.get(
                "names",
                []
            )

            if not isinstance(
                person_names,
                list,
            ):

                continue

            # Prefer the first usable romanized name.
            for name in person_names:

                if not isinstance(
                    name,
                    str,
                ):

                    continue

                name = name.strip()

                if not name:

                    continue

                # We want names containing ASCII letters.
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
    # NAME → SAKUGABOORU TAG
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
    # POST QUALITY
    # ========================================================

    @staticmethod
    def post_quality(post):

        try:

            score = int(
                post.get("score") or 0
            )

        except Exception:

            score = 0

        try:

            favorites = int(
                post.get("fav_count") or 0
            )

        except Exception:

            favorites = 0

        try:

            up_score = int(
                post.get("up_score") or 0
            )

        except Exception:

            up_score = 0

        # Quality formula:
        #
        # Score       = strongest signal
        # Upvotes     = additional signal
        # Favorites   = popularity signal

        quality = (
            max(score, 0) * 3
            + max(up_score, 0)
            + min(favorites, 100) * 0.5
        )

        return quality

    # ========================================================
    # SEARCH ONE ANIMATOR
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

                    # ------------------------------------------------
                    # VIDEO ONLY
                    # ------------------------------------------------

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

                    # ------------------------------------------------
                    # FILE URL
                    # ------------------------------------------------

                    file_url = post.get(
                        "file_url"
                    )

                    if not file_url:

                        continue

                    # ------------------------------------------------
                    # POST ID
                    # ------------------------------------------------

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

                    # ------------------------------------------------
                    # QUALITY
                    # ------------------------------------------------

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

                        "score":
                            post.get(
                                "score",
                                0,
                            ),

                        "fav_count":
                            post.get(
                                "fav_count",
                                0,
                            ),

                        "quality":
                            quality,
                    })

        return tag, clips

    # ========================================================
    # FIND CLIP FOR ANIMATOR
    # ========================================================
    #
    # Used by main.py when selecting battle participants.
    #
    # IMPORTANT:
    # This searches Sakugabooru directly and returns one
    # suitable video clip, or None if no video was found.
    #
    # It does NOT permanently mark the clip as used here.
    # That happens in get_random_clip().
    #
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

            # First search the normal verification range.
            _, clips = await self.search_animator(
                session,
                animator_name,
                max_pages=VERIFY_PAGES,
            )

            # If nothing was found, search deeper.
            if not clips:

                _, clips = await self.search_animator(
                    session,
                    animator_name,
                    max_pages=10,
                )

        if not clips:

            return None

        # Prefer higher-quality clips but keep some randomness.
        weights = []

        for clip in clips:

            quality = float(
                clip.get(
                    "quality",
                    0,
                )
            )

            weight = max(
                1,
                quality + 10,
            )

            weights.append(
                weight
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
            )

            # ====================================================
            # NO VIDEO CLIPS
            # ====================================================

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

            # ====================================================
            # HAS VIDEO CLIPS
            # ====================================================

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

                # More clips + better clips =
                # higher chance of entering battle.
                battle_quality = (
                    best_quality * 0.65
                    + total_quality * 0.20
                    + min(
                        len(clips),
                        50,
                    ) * 2
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

        # Sort strongest first.
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

                # Square-root keeps the pool diverse.
                weight = max(
                    1,
                    quality ** 0.5,
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
                self.name_to_tag(
                    ""
                ),
                [],
            )

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            _, clips = await self.search_animator(
                session,
                animator_input,
                max_pages=5,
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
            count=30,
        )

        available = [
            clip
            for clip in clips
            if clip["id"]
            not in self.used_clips
        ]

        # ====================================================
        # LARGER SEARCH IF NEEDED
        # ====================================================

        if not available:

            async with aiohttp.ClientSession(
                headers=self.get_headers()
            ) as session:

                _, clips = await self.search_animator(
                    session,
                    animator_name,
                    max_pages=10,
                )

            available = [
                clip
                for clip in clips
                if clip["id"]
                not in self.used_clips
            ]

        if not available:

            return None

        # ====================================================
        # WEIGHTED RANDOM CLIP
        # ====================================================

        weights = []

        for clip in available:

            quality = float(
                clip.get(
                    "quality",
                    0,
                )
            )

            # Higher-rated clips are more likely,
            # but the absolute best clip isn't guaranteed.
            weight = max(
                1,
                quality + 10,
            )

            weights.append(
                weight
            )

        clip = random.choices(
            available,
            weights=weights,
            k=1,
        )[0]

        # Mark this clip as used.
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
    # RESET CURRENT BATTLE
    # ========================================================

    def reset(self):

        self.used_clips.clear()

        self.animator_clips.clear()