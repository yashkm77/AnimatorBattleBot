import aiohttp
import asyncio
import json
import os
import random
import math


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://www.sakugabooru.com"

ANIMATOR_INDEX_FILE = "animator_index.json"

POOL_CACHE_FILE = "verified_animators.json"

POSTS_PER_PAGE = 100

# Number of popular Sakugabooru pages used to discover
# candidates.
DISCOVERY_PAGES = 12

# Number of pages searched for an individual animator.
VERIFY_PAGES = 3

# Maximum simultaneous HTTP requests.
REQUEST_CONCURRENCY = 3

VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
}

RETRYABLE_STATUS = {
    429,
    500,
    502,
    503,
    504,
}

# Don't hammer Sakugabooru.
REQUEST_DELAY = 0.15


# ============================================================
# CLIENT
# ============================================================

class SakugabooruClient:

    def __init__(self):

        self.used_clips = set()

        self.animator_clips = {}

        self.verified_animators = {}

        self.animator_name_map = {}

        self._load_cache()

        self._load_animator_index()

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
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) "
                "Version/26.0 Safari/605.1.15",
            "Accept":
                "application/json,text/plain,*/*",
        }

    # ========================================================
    # NORMALIZE NAME
    # ========================================================

    @staticmethod
    def normalize_name(name):

        if not isinstance(name, str):
            return ""

        return (
            name
            .strip()
            .lower()
            .replace("_", " ")
            .replace("-", " ")
        )

    # ========================================================
    # NAME -> TAG
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
    # LOAD CACHE
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

    # ========================================================
    # SAVE CACHE
    # ========================================================

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

    def _load_animator_index(self):

        self.animator_name_map = {}

        if not os.path.exists(
            ANIMATOR_INDEX_FILE
        ):

            print(
                f"⚠️ {ANIMATOR_INDEX_FILE} not found."
            )

            return

        try:

            with open(
                ANIMATOR_INDEX_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

        except Exception as e:

            print(
                f"⚠️ Could not load animator index: {e}"
            )

            return

        people = data.get(
            "people",
            {}
        )

        if not isinstance(
            people,
            dict,
        ):
            return

        for person in people.values():

            if not isinstance(
                person,
                dict,
            ):
                continue

            names = person.get(
                "names",
                []
            )

            if not isinstance(
                names,
                list,
            ):
                continue

            usable = []

            for name in names:

                if not isinstance(
                    name,
                    str,
                ):
                    continue

                name = name.strip()

                if not name:
                    continue

                if not any(
                    c.isascii()
                    and c.isalpha()
                    for c in name
                ):
                    continue

                usable.append(name)

            if not usable:
                continue

            # Every known name points to the preferred
            # display name.
            preferred = usable[0]

            for name in usable:

                normalized = self.normalize_name(
                    name
                )

                if normalized:
                    self.animator_name_map[
                        normalized
                    ] = preferred

        print(
            f"✅ Loaded "
            f"{len(self.animator_name_map):,} "
            f"animator name variants from KFSL."
        )

    # ========================================================
    # GET KFSL MATCH FOR SAKUGABOORU TAG
    # ========================================================

    def match_animator_tag(
        self,
        tag: str,
    ):

        if not isinstance(
            tag,
            str,
        ):
            return None

        normalized = (
            tag
            .strip()
            .lower()
            .replace("_", " ")
            .replace("-", " ")
        )

        normalized = " ".join(
            normalized.split()
        )

        if not normalized:
            return None

        # Exact match against KFSL.
        return self.animator_name_map.get(
            normalized
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

        # Favorites are now a meaningful signal.
        #
        # log1p prevents one huge post from completely
        # dominating everything.
        favorite_value = (
            math.log1p(
                max(favorites, 0)
            ) * 12
        )

        score_value = (
            max(score, 0) * 3
        )

        upvote_value = (
            max(up_score, 0) * 1.5
        )

        return (
            score_value
            + upvote_value
            + favorite_value
        )

    # ========================================================
    # HTTP JSON
    # ========================================================

    async def _get_json(
        self,
        session,
        url,
        params=None,
    ):

        async with self.semaphore:

            for attempt in range(4):

                try:

                    await asyncio.sleep(
                        REQUEST_DELAY
                    )

                    async with session.get(
                        url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(
                            total=25
                        ),
                    ) as response:

                        if response.status in RETRYABLE_STATUS:

                            if attempt < 3:

                                wait_time = (
                                    1.5 ** attempt
                                )

                                print(
                                    f"⚠️ Sakugabooru "
                                    f"HTTP {response.status}; "
                                    f"retrying in "
                                    f"{wait_time:.1f}s"
                                )

                                await asyncio.sleep(
                                    wait_time
                                )

                                continue

                            print(
                                f"⚠️ Sakugabooru "
                                f"HTTP {response.status}; "
                                f"giving up on request."
                            )

                            return None

                        if response.status != 200:

                            print(
                                f"⚠️ Sakugabooru "
                                f"HTTP {response.status}"
                            )

                            return None

                        return await response.json(
                            content_type=None
                        )

                except asyncio.TimeoutError:

                    if attempt < 3:

                        await asyncio.sleep(
                            1.5 ** attempt
                        )

                        continue

                    print(
                        "⏱️ Sakugabooru request timed out."
                    )

                    return None

                except Exception as e:

                    if attempt < 3:

                        await asyncio.sleep(
                            1.5 ** attempt
                        )

                        continue

                    print(
                        f"⚠️ Sakugabooru request error: {e}"
                    )

                    return None

        return None

    # ========================================================
    # DISCOVER POPULAR ANIMATORS
    # ========================================================

    async def discover_popular_animators(
        self,
        count: int,
    ):

        """
        Discover animator candidates from popular VIDEO
        posts rather than checking thousands of KFSL people.

        This is the important performance fix.
        """

        if count < 1:
            return []

        candidates = {}

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            for page in range(
                1,
                DISCOVERY_PAGES + 1,
            ):

                posts = await self._get_json(
                    session,
                    f"{BASE_URL}/post.json",
                    params={
                        "page": page,
                        "limit": POSTS_PER_PAGE,
                        "order": "score",
                    },
                )

                if not isinstance(
                    posts,
                    list,
                ):
                    continue

                if not posts:
                    break

                for post in posts:

                    if not isinstance(
                        post,
                        dict,
                    ):
                        continue

                    ext = str(
                        post.get(
                            "file_ext",
                            ""
                        )
                    ).lower()

                    if ext not in VIDEO_EXTENSIONS:
                        continue

                    tags = post.get(
                        "tags",
                        ""
                    )

                    if isinstance(
                        tags,
                        str,
                    ):

                        raw_tags = tags.split()

                    elif isinstance(
                        tags,
                        list,
                    ):

                        raw_tags = tags

                    else:

                        continue

                    post_quality = (
                        self.post_quality(
                            post
                        )
                    )

                    try:
                        favorites = int(
                            post.get(
                                "fav_count"
                            ) or 0
                        )
                    except Exception:
                        favorites = 0

                    try:
                        score = int(
                            post.get(
                                "score"
                            ) or 0
                        )
                    except Exception:
                        score = 0

                    for raw_tag in raw_tags:

                        animator_name = (
                            self.match_animator_tag(
                                raw_tag
                            )
                        )

                        # If the tag isn't a known KFSL
                        # animator, IGNORE it.
                        #
                        # This prevents:
                        # one_piece
                        # jujutsu_kaisen
                        # naruto
                        # etc.
                        #
                        # from becoming participants.
                        if animator_name is None:
                            continue

                        key = self.normalize_name(
                            animator_name
                        )

                        if not key:
                            continue

                        existing = candidates.get(
                            key
                        )

                        if existing is None:

                            candidates[key] = {
                                "name":
                                    animator_name,

                                "tag":
                                    self.name_to_tag(
                                        animator_name
                                    ),

                                "post_count":
                                    1,

                                "best_quality":
                                    post_quality,

                                "total_quality":
                                    post_quality,

                                "best_favorites":
                                    favorites,

                                "best_score":
                                    score,

                                "example_post_id":
                                    post.get("id"),
                            }

                        else:

                            existing[
                                "post_count"
                            ] += 1

                            existing[
                                "total_quality"
                            ] += post_quality

                            existing[
                                "best_quality"
                            ] = max(
                                existing[
                                    "best_quality"
                                ],
                                post_quality,
                            )

                            existing[
                                "best_favorites"
                            ] = max(
                                existing[
                                    "best_favorites"
                                ],
                                favorites,
                            )

                            existing[
                                "best_score"
                            ] = max(
                                existing[
                                    "best_score"
                                ],
                                score,
                            )

                # Once we have a healthy pool, don't keep
                # hammering Sakugabooru.
                if len(candidates) >= max(
                    count * 5,
                    20,
                ):
                    break

        if not candidates:
            return []

        result = list(
            candidates.values()
        )

        # ----------------------------------------------------
        # Popularity calculation.
        # ----------------------------------------------------

        for candidate in result:

            best = float(
                candidate.get(
                    "best_quality",
                    0,
                )
            )

            total = float(
                candidate.get(
                    "total_quality",
                    0,
                )
            )

            posts = int(
                candidate.get(
                    "post_count",
                    1,
                )
            )

            popularity = (
                best * 0.60
                + total * 0.15
                + min(posts, 20) * 10
            )

            candidate[
                "popularity"
            ] = popularity

        # Strong candidates first.
        result.sort(
            key=lambda x: float(
                x.get(
                    "popularity",
                    0,
                )
            ),
            reverse=True,
        )

        return result

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

        for page in range(
            1,
            max_pages + 1,
        ):

            posts = await self._get_json(
                session,
                f"{BASE_URL}/post.json",
                params={
                    "tags": tag,
                    "page": page,
                    "limit": POSTS_PER_PAGE,
                },
            )

            if not isinstance(
                posts,
                list,
            ):
                continue

            if not posts:
                break

            for post in posts:

                if not isinstance(
                    post,
                    dict,
                ):
                    continue

                ext = str(
                    post.get(
                        "file_ext",
                        ""
                    )
                ).lower()

                if ext not in VIDEO_EXTENSIONS:
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

                # Make sure the requested animator tag is
                # actually present in this post.
                post_tags = post.get(
                    "tags",
                    ""
                )

                if isinstance(
                    post_tags,
                    str,
                ):

                    normalized_tags = {
                        str(x).lower()
                        for x in post_tags.split()
                    }

                elif isinstance(
                    post_tags,
                    list,
                ):

                    normalized_tags = {
                        str(x).lower()
                        for x in post_tags
                    }

                else:

                    normalized_tags = set()

                if tag.lower() not in normalized_tags:

                    # Avoid false matches.
                    continue

                quality = (
                    self.post_quality(
                        post
                    )
                )

                clips.append({
                    "id":
                        post_id,

                    "url":
                        file_url,

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

        key = self.normalize_name(
            animator_name
        )

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

                best_favorites = max(
                    int(
                        clip.get(
                            "fav_count",
                            0,
                        ) or 0
                    )
                    for clip in clips
                )

                # Favor popular/high-quality animators,
                # but don't make one post the only signal.
                battle_quality = (
                    best_quality * 0.60
                    + total_quality * 0.15
                    + min(
                        len(clips),
                        50,
                    ) * 5
                    + math.log1p(
                        best_favorites
                    ) * 15
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
    # CHOOSE BATTLE ANIMATORS
    # ========================================================

    async def choose_battle_animators(
        self,
        count: int,
    ):

        """
        Fast participant selection.

        We discover popular video posts first.

        Then we verify ONLY a small candidate pool.

        We do NOT scan every KFSL animator.
        """

        if count not in (
            2,
            4,
            8,
            16,
        ):
            return []

        candidates = (
            await self.discover_popular_animators(
                max(
                    count * 4,
                    20,
                )
            )
        )

        if not candidates:
            return []

        # ----------------------------------------------------
        # Verify only the strongest candidates.
        # ----------------------------------------------------

        # Keep the verification pool small.
        verify_candidates = candidates[
            :max(count * 3, 12)
        ]

        verified = []

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            tasks = [
                self.verify_animator(
                    candidate["name"],
                    session=session,
                    force=False,
                )
                for candidate in verify_candidates
            ]

            results = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        for result in results:

            if isinstance(
                result,
                Exception,
            ):
                continue

            if not result.get(
                "has_clips"
            ):
                continue

            verified.append(
                result
            )

        if not verified:
            return []

        # ----------------------------------------------------
        # Merge popularity information.
        # ----------------------------------------------------

        popularity_map = {
            self.normalize_name(
                candidate["name"]
            ): candidate
            for candidate in candidates
        }

        for animator in verified:

            key = self.normalize_name(
                animator["name"]
            )

            source = popularity_map.get(
                key
            )

            if source:

                animator[
                    "popularity"
                ] = float(
                    source.get(
                        "popularity",
                        animator.get(
                            "quality",
                            0,
                        ),
                    )
                )

            else:

                animator[
                    "popularity"
                ] = float(
                    animator.get(
                        "quality",
                        0,
                    )
                )

        # ----------------------------------------------------
        # Strongest/popular people should have a MUCH better
        # chance than obscure candidates.
        #
        # But still use weighted randomness so every battle
        # isn't identical.
        # ----------------------------------------------------

        selected = []

        remaining = verified.copy()

        while (
            remaining
            and len(selected) < count
        ):

            weights = []

            for animator in remaining:

                popularity = float(
                    animator.get(
                        "popularity",
                        0,
                    )
                )

                # Square-root keeps diversity.
                weight = max(
                    1.0,
                    math.sqrt(
                        max(
                            popularity,
                            0,
                        )
                    ),
                )

                weights.append(
                    weight
                )

            chosen = random.choices(
                remaining,
                weights=weights,
                k=1,
            )[0]

            selected.append(
                chosen
            )

            remaining.remove(
                chosen
            )

        return selected

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

        return self._choose_quality_clip(
            available
        )

    # ========================================================
    # CHOOSE QUALITY CLIP
    # ========================================================

    @staticmethod
    def _choose_quality_clip(
        clips,
    ):

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

            # Keep randomness, but strongly favor
            # high-quality/favorited posts.
            weight = max(
                1.0,
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

        # ----------------------------------------------------
        # Search a small number of pages.
        # ----------------------------------------------------

        async with aiohttp.ClientSession(
            headers=self.get_headers()
        ) as session:

            _, clips = await self.search_animator(
                session,
                animator_name,
                max_pages=VERIFY_PAGES,
            )

        available = [
            clip
            for clip in clips
            if clip["id"]
            not in self.used_clips
        ]

        # ----------------------------------------------------
        # If nothing found, try deeper once.
        # ----------------------------------------------------

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

        clip = self._choose_quality_clip(
            available
        )

        if clip is None:
            return None

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

        key = self.normalize_name(
            animator_name
        )

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