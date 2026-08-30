from dataclasses import dataclass
from typing import Optional
import random


# ============================================================
# ANIMATOR
# ============================================================

@dataclass
class Animator:

    name: str

    # Sakugabooru clip selected for the current match
    current_clip: Optional[dict] = None

    wins: int = 0
    losses: int = 0
    battles: int = 0

    # Used when choosing strong/popular participants
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
    Tournament manager.

    This class does NOT search Sakugabooru.

    Sakugabooru is responsible for:
        animator -> clips

    This class handles:
        participants
        matches
        winners
        losers
        champion
        tournament progression
        /stop
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

        if mode not in (
            "random",
            "continuous",
        ):

            raise ValueError(
                "Mode must be 'random' or 'continuous'."
            )

        self.animators = animators
        self.mode = mode

        # ----------------------------------------------------
        # Match counter
        # ----------------------------------------------------

        self.match_counter = 0

        # ----------------------------------------------------
        # Tournament state
        # ----------------------------------------------------

        self.phase = "Not Started"

        self.current_match: Optional[Match] = None

        self.match_queue: list[Match] = []

        self.completed_matches: list[Match] = []

        # ----------------------------------------------------
        # Brackets
        # ----------------------------------------------------

        self.winners: list[Animator] = []

        self.losers: list[Animator] = []

        self.eliminated: list[Animator] = []

        # ----------------------------------------------------
        # Champion
        # ----------------------------------------------------

        self.champion: Optional[Animator] = None

        # ----------------------------------------------------
        # Stop flag
        # ----------------------------------------------------

        self.stopped = False

        # ----------------------------------------------------
        # Opening-round flag
        # ----------------------------------------------------

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
    # START TOURNAMENT
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

        self.match_queue.clear()

        # ----------------------------------------------------
        # Create opening matches
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

        # ----------------------------------------------------
        # Odd participant gets automatic advancement
        # ----------------------------------------------------

        if participants:

            self.winners.append(
                participants[0]
            )

        return self.next_matches()

    # ========================================================
    # GET PENDING MATCHES
    # ========================================================

    def get_pending_matches(self):

        if self.stopped:
            return []

        return self.match_queue.copy()

    # ========================================================
    # NEXT MATCHES
    # ========================================================

    def next_matches(self):

        """
        Return all matches currently waiting in the queue.

        This method exists because main.py processes an entire
        round at a time:

            matches = tournament.start()

            ...

            matches = tournament.next_matches()

        It also prevents the missing-attribute error:
            AnimatorBattle has no attribute 'next_matches'
        """

        if self.stopped:
            return []

        return self.match_queue.copy()

    # ========================================================
    # GET NEXT MATCH
    # ========================================================

    def get_next_match(self):

        if self.stopped:
            return None

        # Current match is still active
        if self.current_match is not None:

            return self.current_match

        # Queue has another match
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

        # ----------------------------------------------------
        # Make sure this is the active match.
        #
        # main.py processes matches directly from the queue,
        # so current_match may be None here.
        #
        # Therefore we only validate it when one exists.
        # ----------------------------------------------------

        if (
            self.current_match is not None
            and match.match_id
            != self.current_match.match_id
        ):

            raise ValueError(
                "This is not the current battle match."
            )

        match.set_result(winner)

        loser = match.loser

        if loser is None:

            raise RuntimeError(
                "Match has no loser."
            )

        self.completed_matches.append(
            match
        )

        # ----------------------------------------------------
        # WINNERS BRACKET
        # ----------------------------------------------------

        if match.bracket == "Winners":

            self.winners.append(
                winner
            )

            self.losers.append(
                loser
            )

        # ----------------------------------------------------
        # LOSERS BRACKET
        # ----------------------------------------------------

        elif match.bracket == "Losers":

            self.losers.append(
                winner
            )

            self.eliminate(
                loser
            )

        # ----------------------------------------------------
        # GRAND FINAL
        # ----------------------------------------------------

        elif match.bracket == "Grand Final":

            self.champion = winner

            self.phase = "Finished"

        # ----------------------------------------------------
        # Clear active match
        # ----------------------------------------------------

        self.current_match = None

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Only prepare another stage when the current queue
        # has completely finished.
        # ----------------------------------------------------

        if (
            self.phase != "Finished"
            and not self.match_queue
        ):

            self.prepare_next_round()

        return True

    # ========================================================
    # PREPARE NEXT ROUND
    # ========================================================

    def prepare_next_round(self):

        if self.stopped:
            return

        # ----------------------------------------------------
        # Do not build another round while matches are queued.
        # ----------------------------------------------------

        if self.match_queue:
            return

        # ----------------------------------------------------
        # Winners bracket
        # ----------------------------------------------------

        if len(self.winners) >= 2:

            self.build_winners_round()

            return

        # ----------------------------------------------------
        # If only one winner remains, check losers.
        # ----------------------------------------------------

        if (
            len(self.winners) == 1
            and len(self.losers) >= 2
        ):

            self.build_losers_round()

            return

        # ----------------------------------------------------
        # Losers bracket
        # ----------------------------------------------------

        if len(self.losers) >= 2:

            self.build_losers_round()

            return

        # ----------------------------------------------------
        # Grand final
        # ----------------------------------------------------

        if (
            len(self.winners) == 1
            and len(self.losers) == 1
        ):

            winners_champion = (
                self.winners[0]
            )

            losers_champion = (
                self.losers[0]
            )

            self.winners.clear()
            self.losers.clear()

            self.phase = "Grand Final"

            match = self.create_match(
                winners_champion,
                losers_champion,
                "Grand Final",
            )

            if match:

                self.match_queue.append(
                    match
                )

            return

        # ----------------------------------------------------
        # Only one winner remains
        # ----------------------------------------------------

        if len(self.winners) == 1:

            self.champion = (
                self.winners[0]
            )

            self.phase = "Finished"

    # ========================================================
    # BUILD WINNERS ROUND
    # ========================================================

    def build_winners_round(self):

        if self.stopped:
            return []

        if len(self.winners) < 2:
            return []

        participants = self.winners.copy()

        self.winners.clear()

        random.shuffle(participants)

        matches = []

        while len(participants) >= 2:

            animator_a = participants.pop(0)
            animator_b = participants.pop(0)

            match = self.create_match(
                animator_a,
                animator_b,
                "Winners",
            )

            if match:

                matches.append(match)

                self.match_queue.append(
                    match
                )

        # ----------------------------------------------------
        # Automatic advancement
        # ----------------------------------------------------

        if participants:

            self.winners.append(
                participants[0]
            )

        self.phase = "Winners Bracket"

        return matches

    # ========================================================
    # BUILD LOSERS ROUND
    # ========================================================

    def build_losers_round(self):

        if self.stopped:
            return []

        if len(self.losers) < 2:
            return []

        participants = self.losers.copy()

        self.losers.clear()

        random.shuffle(participants)

        matches = []

        while len(participants) >= 2:

            animator_a = participants.pop(0)
            animator_b = participants.pop(0)

            match = self.create_match(
                animator_a,
                animator_b,
                "Losers",
            )

            if match:

                matches.append(match)

                self.match_queue.append(
                    match
                )

        # ----------------------------------------------------
        # Automatic advancement
        # ----------------------------------------------------

        if participants:

            self.losers.append(
                participants[0]
            )

        self.phase = "Losers Bracket"

        return matches

    # ========================================================
    # ELIMINATE
    # ========================================================

    def eliminate(
        self,
        animator: Animator,
    ):

        if animator not in self.eliminated:

            self.eliminated.append(
                animator
            )

        if animator in self.winners:

            self.winners.remove(
                animator
            )

        if animator in self.losers:

            self.losers.remove(
                animator
            )

    # ========================================================
    # CHECK FINISHED
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

        """
        Completely terminate the tournament.

        This means:
            END THE ENTIRE GAME.
        """

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

            "losers_remaining": len(
                self.losers
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


