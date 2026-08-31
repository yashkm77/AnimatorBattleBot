import aiohttp
import asyncio
import json
import os
import random
import urllib.parse


BASE_URL = "https://www.sakugabooru.com"

ANIMATOR_INDEX_FILE = "animator_index.json"

POOL_CACHE_FILE = "verified_animators.json"

VERIFY_PAGES = 3

POSTS_PER_PAGE = 100

REQUEST_CONCURRENCY = 5

MAX_503_RETRIES = 3


class SakugabooruClient:

    def __init__(self):

        self.used_clips = set()

        self.animator_clips = {}

        self.verified_animators = {}

        self._load_cache()

        self.semaphore = asyncio.Semaphore(
            REQUEST_CONCURRENCY
        )

    # ========================================================
    # HEADERS
    # ========================================================

    @staticmethod
    def get_headers():

        return {
            "User-Agent":
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X) "
                "AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) "
                "Version/26.0 Safari/605.1.15",
            "Accept":
                "application/json,text/plain,*/*",
            "Referer":
                "https://www.sakugabooru.com/",
        }

    # ========================================================
    # CACHE
    # ========================================================

    def _load_cache(self):

        if not os.path.exists(
            POOL_CACHE_FILE
        ):

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

            temp_file = (
                POOL_CACHE_FILE + ".tmp"
            )

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
    # LOAD KFSL ANIMATOR INDEX
    # ========================================================

    def load_animator_index(self):

        if not os.path.exists(
            ANIMATOR_INDEX_FILE
        ):

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

            if not isinstance(
                person,
                dict,
            ):
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
    # QUALITY
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

        # Favorites are deliberately weighted strongly.
        # This helps genuinely popular Sakugabooru posts
        # appear more often.
        quality = (
            max(score, 0) * 3.0
            + max(up_score, 0) * 1.5
            + min(favorites, 500) * 1.5
        )

        return quality

    # ========================================================
    # HTTP GET WITH 503 RETRY
    # ========================================================

    async def get_posts(
        self,
        session,
        url,
        animator_name,
    ):

        for attempt in range(
            MAX_503_RETRIES + 1
        ):

            try:

                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(
                        total=25
                    ),
                ) as response:

                    if response.status == 200:

                        return await response.json(
                            content_type=None
                        )

                    if response.status == 503:

                        if attempt < MAX_503_RETRIES:

                            wait_time = (
                                2 ** attempt
                            )

                            print(
                                f"⚠️ Sakugabooru 503 for "
                                f"{animator_name} — "
                                f"retrying in "
                                f"{wait_time}s..."
                            )

                            await asyncio.sleep(
                                wait_time
                            )

                            continue

                        print(
                            f"⚠️ Sakugabooru 503 for "
                            f"{animator_name} "
                            f"after retries."
                        )

                        return []

                    print(
                        f"⚠️ Sakugabooru returned HTTP "
                        f"{response.status} for "
                        f"{animator_name}"
                    )

                    return []

            except asyncio.TimeoutError:

                if attempt < MAX_503_RETRIES:

                    await asyncio.sleep(
                        1 + attempt
                    )

                    continue

                print(
                    f"⏱️ Sakugabooru timeout for "
                    f"{animator_name}"
                )

                return []

            except Exception as e:

                if attempt < MAX_503_RETRIES:

                    await asyncio.sleep(
                        1 + attempt
                    )

                    continue

                print(
                    f"Sakugabooru search error "
                    f"for {animator_name}: {e}"
                )

                return []

        return []

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

        encoded_tag = urllib.parse.quote(
            tag,
            safe=""
        )

        async with self.semaphore:

            for page in range(
                1,
                max_pages + 1,
            ):

                url = (
                    f"{BASE_URL}/post.json"
                    f"?tags={encoded_tag}"
                    f"&page={page}"
                    f"&limit={POSTS_PER_PAGE}"
                )

                posts = await self.get_posts(
                    session,
                    url,
                    animator_name,
                )

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

                result = {
                    "name": animator_name,
                    "tag": tag,
                    "has_clips": False,
                    "clip_count": 0,
                    "best_quality": 0,
                    "total_quality": 0,
                    "best_favorites": 0,
                    "quality": 0,
                }

            else:

                qualities = [
                    float(
                        clip.get(
                            "quality",
                            0
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

                best_favorites = max(
                    int(
                        clip.get(
                            "fav_count",
                            0
                        ) or 0
                    )
                    for clip in clips
                )

                # Stronger quality formula.
                battle_quality = (
                    best_quality * 0.60
                    + total_quality * 0.15
                    + best_favorites * 10
                    + min(
                        len(clips),
                        100,
                    ) * 5
                )

                result = {
                    "name": animator_name,
                    "tag": tag,
                    "has_clips": True,
                    "clip_count": len(clips),
                    "best_quality": best_quality,
                    "total_quality": total_quality,
                    "best_favorites": best_favorites,
                    "quality": battle_quality,
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
        animator_names,
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
                verified.append(result)

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

        # ----------------------------------------------------
        # USE EXISTING CACHE FIRST
        # ----------------------------------------------------

        cached_pool = []

        for name in names:

            cached = self.verified_animators.get(
                name.lower()
            )

            if not cached:
                continue

            if not cached.get(
                "has_clips"
            ):
                continue

            cached_pool.append(
                cached
            )

        # If cache already has a good pool, don't hammer
        # Sakugabooru with thousands of requests.
        if (
            not force
            and len(cached_pool) >= 20
        ):

            cached_pool.sort(
                key=lambda x: float(
                    x.get(
                        "quality",
                        0
                    )
                ),
                reverse=True,
            )

            print(
                f"✅ Using {len(cached_pool):,} "
                f"cached Sakugabooru animators."
            )

            return cached_pool

        # ----------------------------------------------------
        # INITIAL BUILD
        # ----------------------------------------------------

        print(
            f"🔎 Building animator pool from "
            f"{len(names):,} KFSL names..."
        )

        # Don't request every single animator at once.
        # Select a large random sample so the bot doesn't
        # spend all night hitting Sakugabooru.
        sample_size = min(
            300,
            len(names)
        )

        sample = random.sample(
            names,
            sample_size
        )

        # Always include cached animators.
        for name in names:

            if name.lower() in self.verified_animators:

                if name not in sample:

                    sample.append(name)

        verified = await self.verify_many(
            sample,
            force=force,
        )

        if not verified:

            # Fall back to whatever cache exists.
            return cached_pool

        verified.sort(
            key=lambda x: float(
                x.get(
                    "quality",
                    0
                )
            ),
            reverse=True,
        )

        print(
            f"✅ Found {len(verified):,} "
            f"verified animators."
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

        # ----------------------------------------------------
        # TOP QUALITY POOL
        # ----------------------------------------------------

        pool = [
            animator
            for animator in pool
            if animator.get(
                "has_clips"
            )
        ]

        pool.sort(
            key=lambda x: float(
                x.get(
                    "quality",
                    0
                )
            ),
            reverse=True,
        )

        # Keep popular/high-quality animators available,
        # while still allowing less-famous people.
        top_pool_size = min(
            max(
                count * 12,
                30
            ),
            len(pool)
        )

        candidates = pool[
            :top_pool_size
        ].copy()

        selected = []

        for _ in range(count):

            if not candidates:
                break

            weights = []

            for animator in candidates:

                quality = max(
                    float(
                        animator.get(
                            "quality",
                            0
                        )
                    ),
                    1
                )

                # Square root prevents one gigantic
                # favorite count from dominating everything.
                weight = max(
                    1,
                    quality ** 0.5
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

        weights = []

        for clip in available:

            quality = max(
                float(
                    clip.get(
                        "quality",
                        0
                    )
                ),
                1
            )

            # Popular clips have a higher probability,
            # but aren't guaranteed every time.
            weight = max(
                1,
                quality + 10
            )

            weights.append(
                weight
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