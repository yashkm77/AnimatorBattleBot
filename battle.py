from dataclasses import dataclass
from typing import Optional
import random


# ============================================================
# ANIMATOR
# ============================================================

@dataclass
class Animator:

    name: str

    # Optional metadata from Sakugabooru.
    # This is NOT displayed as the anime name.
    popularity: float = 0.0

    current_clip: Optional[dict] = None

    wins: int = 0
    losses: int = 0
    battles: int = 0

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

    bracket: str = "Winners"

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
    Single-elimination animator tournament.

    IMPORTANT:
    This class controls tournament progression only.

    Sakugabooru searching is handled by sakugabooru.py.

    A 2-person battle:
        Match 1
        -> winner
        -> champion
        -> STOP

    A 4-person battle:
        Match 1
        Match 2
        -> Final
        -> champion

    An 8-person battle:
        4 quarterfinals
        -> 2 semifinals
        -> final

    This intentionally avoids the old broken losers-bracket
    logic which could continue indefinitely.
    """

    def __init__(
        self,
        animators: list[Animator],
        mode: str = "random",
    ):

        if len(animators) < 2:
            raise ValueError(
                "At least 2 animators are required."
            )

        if len(animators) not in (
            2,
            4,
            8,
            16,
        ):
            raise ValueError(
                "Battle size must be 2, 4, 8 or 16."
            )

        if mode not in (
            "random",
            "continuous",
        ):
            raise ValueError(
                "Mode must be 'random' or 'continuous'."
            )

        self.animators = animators
        self.mode = mode

        # Match numbering.
        self.match_counter = 0

        # Current stage.
        self.phase = "Not Started"

        # Active match.
        self.current_match: Optional[Match] = None

        # Matches waiting to be played.
        self.match_queue: list[Match] = []

        # Completed matches.
        self.completed_matches: list[Match] = []

        # Current round winners.
        self.winners: list[Animator] = []

        # Compatibility fields.
        self.losers: list[Animator] = []
        self.eliminated: list[Animator] = []

        # Champion.
        self.champion: Optional[Animator] = None

        # Stop flag.
        self.stopped = False

        # Tournament started.
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
        bracket: str = "Winners",
    ):

        if self.stopped:
            return None

        return Match(
            match_id=self.next_match_id(),
            animator_a=animator_a,
            animator_b=animator_b,
            bracket=bracket,
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

        self.phase = "Opening Round"

        participants = self.animators.copy()

        random.shuffle(participants)

        self.winners.clear()
        self.losers.clear()
        self.eliminated.clear()
        self.match_queue.clear()
        self.completed_matches.clear()

        # Reset participant statistics.
        for animator in participants:
            animator.reset()

        # ----------------------------------------------------
        # Create first round.
        # ----------------------------------------------------

        while len(participants) >= 2:

            animator_a = participants.pop(0)
            animator_b = participants.pop(0)

            match = self.create_match(
                animator_a,
                animator_b,
                "Winners",
            )

            if match:
                self.match_queue.append(match)

        # Should never happen because battle sizes are powers
        # of two, but keep this safe.
        if participants:
            self.winners.append(
                participants[0]
            )

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
    # MANUAL NEXT MATCH
    # ========================================================

    def next_match(self):

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

        if winner not in (
            match.animator_a,
            match.animator_b,
        ):
            raise ValueError(
                "Winner must be one of the match participants."
            )

        match.set_result(winner)

        loser = match.loser

        self.completed_matches.append(
            match
        )

        # ----------------------------------------------------
        # Current round winner.
        # ----------------------------------------------------

        self.winners.append(
            winner
        )

        if loser is not None:
            self.eliminated.append(
                loser
            )

        # ----------------------------------------------------
        # Clear current match.
        # ----------------------------------------------------

        self.current_match = None

        # ----------------------------------------------------
        # If other matches in this same round remain,
        # DO NOT create the next round yet.
        # ----------------------------------------------------

        if self.match_queue:
            return True

        # ----------------------------------------------------
        # Current round is completely finished.
        # ----------------------------------------------------

        self.prepare_next_round()

        return True

    # ========================================================
    # PREPARE NEXT ROUND
    # ========================================================

    def prepare_next_round(self):

        if self.stopped:
            return

        if self.champion is not None:
            self.phase = "Finished"
            return

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # If exactly ONE animator remains, that animator is
        # champion.
        #
        # This is what fixes the endless Match 459 issue.
        # ----------------------------------------------------

        if len(self.winners) == 1:

            self.champion = self.winners[0]
            self.phase = "Finished"

            return

        # ----------------------------------------------------
        # Need at least two winners to create another round.
        # ----------------------------------------------------

        if len(self.winners) < 2:

            self.phase = "Finished"

            if self.winners:
                self.champion = self.winners[0]

            return

        # ----------------------------------------------------
        # Build next single-elimination round.
        # ----------------------------------------------------

        participants = self.winners.copy()

        self.winners.clear()

        random.shuffle(participants)

        self.match_queue.clear()

        while len(participants) >= 2:

            animator_a = participants.pop(0)
            animator_b = participants.pop(0)

            match = self.create_match(
                animator_a,
                animator_b,
                "Winners",
            )

            if match:
                self.match_queue.append(match)

        # Safety for odd counts.
        if participants:
            self.winners.append(
                participants[0]
            )

        remaining = len(
            self.match_queue
        )

        if remaining == 1:
            self.phase = "Final"
        else:
            self.phase = "Next Round"

    # ========================================================
    # FINISHED
    # ========================================================

    def is_finished(self):

        return (
            self.champion is not None
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

        self.phase = "Not Started"

        self.current_match = None

        self.match_queue.clear()

        self.completed_matches.clear()

        self.winners.clear()

        self.losers.clear()

        self.eliminated.clear()

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

            "phase": self.phase,

            "animators": len(
                self.animators
            ),

            "completed_matches": len(
                self.completed_matches
            ),

            "pending_matches": len(
                self.match_queue
            ),

            "eliminated": len(
                self.eliminated
            ),

            "winners_remaining": len(
                self.winners
            ),

            "champion": (
                self.champion.name
                if self.champion
                else None
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

            "animator_a":
                match.animator_a.name,

            "animator_b":
                match.animator_b.name,

            "votes_a":
                match.votes_a,

            "votes_b":
                match.votes_b,

            "completed":
                match.completed,
        }