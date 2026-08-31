from dataclasses import dataclass
from typing import Optional
import random


# ============================================================
# ANIMATOR
# ============================================================

@dataclass
class Animator:

    name: str

    # Clip selected for the current match
    current_clip: Optional[dict] = None

    wins: int = 0
    losses: int = 0
    battles: int = 0

    # Used for weighted participant selection
    popularity: float = 0.0

    def reset(self):
        self.current_clip = None
        self.wins = 0
        self.losses = 0
        self.battles = 0


# ============================================================
# MATCH
# ============================================================

@dataclass
class Match:

    match_id: int

    animator_a: Animator
    animator_b: Animator

    bracket: str = "Battle"

    votes_a: int = 0
    votes_b: int = 0

    winner: Optional[Animator] = None
    loser: Optional[Animator] = None

    completed: bool = False

    def set_result(self, winner: Animator):

        if self.completed:
            raise ValueError(
                "This match is already complete."
            )

        if winner not in (
            self.animator_a,
            self.animator_b,
        ):
            raise ValueError(
                "Winner must be one of the match participants."
            )

        self.winner = winner

        if winner == self.animator_a:
            self.loser = self.animator_b
        else:
            self.loser = self.animator_a

        self.animator_a.battles += 1
        self.animator_b.battles += 1

        winner.wins += 1

        if self.loser:
            self.loser.losses += 1

        self.completed = True


# ============================================================
# ANIMATOR BATTLE
# ============================================================

class AnimatorBattle:

    """
    Fixed-match animator battle.

    IMPORTANT:

        rounds = number of matches

    Example:

        rounds = 2
            -> Match 1
            -> Match 2
            -> FINISHED

        rounds = 8
            -> Match 1
            -> ...
            -> Match 8
            -> FINISHED

    This class does NOT search Sakugabooru.
    """

    def __init__(
        self,
        animators: list[Animator],
        mode: str = "random",
        rounds: int = 1,
    ):

        if len(animators) < 2:
            raise ValueError(
                "At least 2 animators are required."
            )

        if mode not in (
            "random",
            "continuous",
        ):
            raise ValueError(
                "Mode must be 'random' or 'continuous'."
            )

        if rounds < 1:
            raise ValueError(
                "Rounds must be at least 1."
            )

        self.animators = animators
        self.mode = mode
        self.rounds = rounds

        # Match IDs are global inside this battle.
        self.match_counter = 0

        # Number of completed matches.
        self.completed_match_count = 0

        self.phase = "Not Started"

        self.current_match: Optional[Match] = None

        self.match_queue: list[Match] = []

        self.completed_matches: list[Match] = []

        self.champion: Optional[Animator] = None

        self.stopped = False
        self.started = False

    # ========================================================
    # MATCH ID
    # ========================================================

    def next_match_id(self):

        self.match_counter += 1
        return self.match_counter

    # ========================================================
    # CREATE MATCH
    # ========================================================

    def create_match(
        self,
        animator_a: Animator,
        animator_b: Animator,
    ):

        if self.stopped:
            return None

        return Match(
            match_id=self.next_match_id(),
            animator_a=animator_a,
            animator_b=animator_b,
            bracket="Battle",
        )

    # ========================================================
    # START
    # ========================================================

    def start(self):

        if self.stopped:
            return []

        if self.started:
            return self.next_matches()

        self.started = True
        self.phase = "Battle"

        self.match_queue.clear()

        # ----------------------------------------------------
        # We create exactly `rounds` matches.
        #
        # The caller provides enough unique animators.
        # ----------------------------------------------------

        participants = self.animators.copy()

        random.shuffle(participants)

        for _ in range(self.rounds):

            if len(participants) < 2:
                break

            animator_a = participants.pop(0)
            animator_b = participants.pop(0)

            match = self.create_match(
                animator_a,
                animator_b,
            )

            if match:
                self.match_queue.append(match)

        return self.next_matches()

    # ========================================================
    # NEXT MATCHES
    # ========================================================

    def next_matches(self):

        if self.stopped:
            return []

        return self.match_queue.copy()

    # ========================================================
    # GET NEXT MATCH
    # ========================================================

    def get_next_match(self):

        if self.stopped:
            return None

        if self.current_match is not None:
            return self.current_match

        if self.match_queue:

            self.current_match = (
                self.match_queue.pop(0)
            )

            return self.current_match

        return None

    # ========================================================
    # NEXT MATCH
    # ========================================================

    def next_match(self):

        if self.stopped:
            return None

        return self.get_next_match()

    # ========================================================
    # RECORD RESULT
    # ========================================================

    def record_result(
        self,
        match: Match,
        winner: Animator,
    ):

        if self.stopped:
            return False

        if match.completed:
            return False

        match.set_result(winner)

        self.completed_matches.append(match)

        self.completed_match_count += 1

        self.current_match = None

        # ----------------------------------------------------
        # EXACT MATCH LIMIT
        # ----------------------------------------------------

        if self.completed_match_count >= self.rounds:

            self.phase = "Finished"

            # This battle is not a tournament.
            # There is no grand final.
            self.champion = None

            self.match_queue.clear()

            return True

        return True

    # ========================================================
    # CHECK FINISHED
    # ========================================================

    def is_finished(self):

        return (
            self.stopped
            or self.completed_match_count >= self.rounds
            or self.phase == "Finished"
        )

    # ========================================================
    # STOP
    # ========================================================

    def stop(self):

        self.stopped = True

        self.phase = "Stopped"

        self.current_match = None

        self.match_queue.clear()

    # ========================================================
    # RESET
    # ========================================================

    def reset(self):

        self.match_counter = 0
        self.completed_match_count = 0

        self.phase = "Not Started"

        self.current_match = None

        self.match_queue.clear()

        self.completed_matches.clear()

        self.champion = None

        self.stopped = False
        self.started = False

        for animator in self.animators:
            animator.reset()

    # ========================================================
    # STATUS
    # ========================================================

    def status(self):

        return {
            "mode": self.mode,

            "rounds": self.rounds,

            "phase": self.phase,

            "animators": len(self.animators),

            "completed_matches": len(
                self.completed_matches
            ),

            "remaining_matches": max(
                0,
                self.rounds - self.completed_match_count,
            ),

            "pending_matches": len(
                self.match_queue
            ),

            "stopped": self.stopped,
        }

    # ========================================================
    # CURRENT MATCH INFO
    # ========================================================

    def current_match_info(self):

        match = self.current_match

        if match is None:
            return None

        return {
            "match_id": match.match_id,

            "bracket": match.bracket,

            "animator_a": (
                match.animator_a.name
            ),

            "animator_b": (
                match.animator_b.name
            ),

            "votes_a": match.votes_a,

            "votes_b": match.votes_b,

            "completed": match.completed,
        }