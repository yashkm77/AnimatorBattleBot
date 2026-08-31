from dataclasses import dataclass
from typing import Optional
import random


# ============================================================
# ANIMATOR
# ============================================================

@dataclass
class Animator:

    name: str

    # Sakugabooru clip used by the current battle.
    current_clip: Optional[dict] = None

    wins: int = 0
    losses: int = 0
    battles: int = 0

    # Sakugabooru popularity / quality.
    popularity: float = 0.0

    def reset(self):

        self.current_clip = None

        self.wins = 0
        self.losses = 0
        self.battles = 0

        self.popularity = 0.0


# ============================================================
# MATCH
# ============================================================

@dataclass
class Match:

    match_id: int

    animator_a: Animator
    animator_b: Animator

    # Examples:
    # "Round 1"
    # "Round 2"
    # "Final"
    bracket: str = "Round 1"

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

        # Record battle statistics.
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

    Tournament structure:

        rounds=1
            2 animators
            A vs B
            winner = champion

        rounds=2
            4 animators

            A vs B -> A
            C vs D -> C

            A vs C -> champion

        rounds=3
            8 animators

            Round 1:
                A vs B
                C vs D
                E vs F
                G vs H

            Round 2:
                winners vs winners

            Final:
                final two winners

        rounds=4
            16 animators

            Round 1:
                8 matches

            Round 2:
                4 matches

            Round 3:
                2 matches

            Final:
                1 match

    IMPORTANT:

    There is NO losers bracket.

    Once an animator loses a match,
    that animator is permanently eliminated.

    The number of animators required is:

        2 ** rounds
    """

    def __init__(
        self,
        animators: list[Animator],
        rounds: int = 1,
        mode: str = "random",
    ):

        if not animators:
            raise ValueError(
                "At least 2 animators are required."
            )

        if rounds < 1:
            raise ValueError(
                "Rounds must be at least 1."
            )

        if rounds > 10:
            raise ValueError(
                "Rounds cannot be greater than 10."
            )

        if mode not in (
            "random",
            "continuous",
        ):
            raise ValueError(
                "Mode must be 'random' or 'continuous'."
            )

        # Number of participants required.
        required_animators = 2 ** rounds

        if len(animators) != required_animators:
            raise ValueError(
                f"{rounds} rounds requires exactly "
                f"{required_animators} animators."
            )

        self.animators = animators

        self.rounds = rounds

        self.mode = mode

        # Current tournament round.
        self.current_round = 0

        # Global match counter.
        self.match_counter = 0

        self.phase = "Not Started"

        # Match currently being played.
        self.current_match: Optional[Match] = None

        # Matches waiting to be played.
        self.match_queue: list[Match] = []

        # Matches already completed.
        self.completed_matches: list[Match] = []

        # Winners advancing from the current round.
        self.winners: list[Animator] = []

        # All eliminated animators.
        self.eliminated: list[Animator] = []

        # Participants in the current round.
        self.current_participants: list[Animator] = []

        # Tournament champion.
        self.champion: Optional[Animator] = None

        # Tournament control.
        self.stopped = False

        self.started = False

    # ========================================================
    # MATCH ID
    # ========================================================

    def next_match_id(self):

        self.match_counter += 1

        return self.match_counter

    # ========================================================
    # REQUIRED ANIMATORS
    # ========================================================

    @property
    def required_animators(self):

        return 2 ** self.rounds

    # ========================================================
    # CREATE MATCH
    # ========================================================

    def create_match(
        self,
        animator_a: Animator,
        animator_b: Animator,
        bracket: Optional[str] = None,
    ):

        if self.stopped:
            return None

        if bracket is None:

            if self.current_round == self.rounds:
                bracket = "Final"
            else:
                bracket = f"Round {self.current_round}"

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

        # Prevent starting the same tournament twice.
        if self.started:
            return self.get_pending_matches()

        self.started = True

        self.current_round = 1

        self.phase = f"Round {self.current_round}"

        # Make a copy so the original animator list
        # isn't modified.
        participants = self.animators.copy()

        # Randomize the initial tournament bracket ONCE.
        random.shuffle(participants)

        self.current_participants = participants.copy()

        self.winners.clear()

        self.eliminated.clear()

        self.match_queue.clear()

        self.completed_matches.clear()

        self.current_match = None

        self.champion = None

        self.match_counter = 0

        # Create first round.
        self.build_round_matches(participants)

        return self.get_pending_matches()

    # ========================================================
    # BUILD ROUND MATCHES
    # ========================================================

    def build_round_matches(
        self,
        participants: list[Animator],
    ):

        if self.stopped:
            return []

        if len(participants) < 2:
            return []

        # Every new round starts with an empty winner list.
        self.winners.clear()

        matches = []

        # Copy the list.
        #
        # IMPORTANT:
        # Do NOT shuffle here.
        #
        # The initial bracket is already randomized in start().
        # For later rounds, winners should be paired according
        # to the previous round's results.
        participants = participants.copy()

        self.current_participants = participants.copy()

        while len(participants) >= 2:

            animator_a = participants.pop(0)

            animator_b = participants.pop(0)

            if self.current_round == self.rounds:

                bracket = "Final"

            else:

                bracket = f"Round {self.current_round}"

            match = self.create_match(
                animator_a,
                animator_b,
                bracket,
            )

            if match:

                matches.append(match)

                self.match_queue.append(match)

        self.phase = (
            "Final"
            if self.current_round == self.rounds
            else f"Round {self.current_round}"
        )

        return matches

    # ========================================================
    # PENDING MATCHES
    # ========================================================

    def get_pending_matches(self):

        if self.stopped:
            return []

        return self.match_queue.copy()

    # ========================================================
    # NEXT MATCHES
    # ========================================================

    def next_matches(self):

        return self.get_pending_matches()

    # ========================================================
    # GET NEXT MATCH
    # ========================================================

    def get_next_match(self):

        if self.stopped:
            return None

        # If a match is currently active,
        # return that same match.
        if self.current_match is not None:

            return self.current_match

        if not self.match_queue:

            return None

        # Remove match from queue so it cannot
        # accidentally be processed twice.
        match = self.match_queue.pop(0)

        self.current_match = match

        return match

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

        # If there is an active match, make sure
        # the supplied match is that match.
        if (
            self.current_match is not None
            and match.match_id != self.current_match.match_id
        ):

            raise ValueError(
                "This is not the current battle match."
            )

        # Make sure the winner actually participated.
        if winner not in (
            match.animator_a,
            match.animator_b,
        ):

            raise ValueError(
                "Winner is not part of this match."
            )

        # Record result.
        match.set_result(winner)

        loser = match.loser

        if loser is None:

            raise RuntimeError(
                "Match has no loser."
            )

        # Save completed match.
        self.completed_matches.append(match)

        # ----------------------------------------------------
        # WINNER ADVANCES
        # ----------------------------------------------------

        self.winners.append(winner)

        # ----------------------------------------------------
        # LOSER IS PERMANENTLY ELIMINATED
        # ----------------------------------------------------

        self.eliminate(loser)

        # ----------------------------------------------------
        # CLEAR CURRENT MATCH
        # ----------------------------------------------------

        self.current_match = None

        # ----------------------------------------------------
        # CURRENT ROUND FINISHED?
        # ----------------------------------------------------

        if not self.match_queue:

            self.prepare_next_round()

        return True

    # ========================================================
    # PREPARE NEXT ROUND
    # ========================================================

    def prepare_next_round(self):

        if self.stopped:
            return

        # Never create a new round while matches
        # from the current round are still waiting.
        if self.match_queue:
            return

        # ----------------------------------------------------
        # CHAMPION
        # ----------------------------------------------------

        if len(self.winners) == 1:

            self.champion = self.winners[0]

            self.phase = "Finished"

            return

        # ----------------------------------------------------
        # SAFETY CHECK
        # ----------------------------------------------------

        if len(self.winners) < 2:

            return

        # ----------------------------------------------------
        # ADVANCE TO NEXT ROUND
        # ----------------------------------------------------

        self.current_round += 1

        if self.current_round > self.rounds:

            # Safety fallback.
            self.champion = self.winners[0]

            self.phase = "Finished"

            return

        # The winners become the participants
        # of the next round.
        participants = self.winners.copy()

        self.build_round_matches(participants)

    # ========================================================
    # ELIMINATE
    # ========================================================

    def eliminate(
        self,
        animator: Animator,
    ):

        if animator not in self.eliminated:

            self.eliminated.append(animator)

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

        self.current_round = 0

        self.phase = "Not Started"

        self.current_match = None

        self.match_queue.clear()

        self.completed_matches.clear()

        self.winners.clear()

        self.eliminated.clear()

        self.current_participants.clear()

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

            "current_round": self.current_round,

            "phase": self.phase,

            "animators": len(self.animators),

            "required_animators": self.required_animators,

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

            "round": self.current_round,

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

    # ========================================================
    # BRACKET
    # ========================================================

    def bracket(self):

        """
        Returns a simple tournament bracket summary.
        """

        result = []

        # ----------------------------------------------------
        # COMPLETED MATCHES
        # ----------------------------------------------------

        for match in self.completed_matches:

            result.append({
                "match_id": match.match_id,

                "round": match.bracket,

                "animator_a": match.animator_a.name,

                "animator_b": match.animator_b.name,

                "votes_a": match.votes_a,

                "votes_b": match.votes_b,

                "winner": (
                    match.winner.name
                    if match.winner
                    else None
                ),

                "loser": (
                    match.loser.name
                    if match.loser
                    else None
                ),
            })

        # ----------------------------------------------------
        # PENDING MATCHES
        # ----------------------------------------------------

        for match in self.match_queue:

            result.append({
                "match_id": match.match_id,

                "round": match.bracket,

                "animator_a": match.animator_a.name,

                "animator_b": match.animator_b.name,

                "votes_a": match.votes_a,

                "votes_b": match.votes_b,

                "winner": None,

                "loser": None,
            })

        # ----------------------------------------------------
        # CURRENT MATCH
        # ----------------------------------------------------

        if self.current_match is not None:

            match = self.current_match

            # Avoid duplicate entry.
            if not any(
                item["match_id"] == match.match_id
                for item in result
            ):

                result.append({
                    "match_id": match.match_id,

                    "round": match.bracket,

                    "animator_a": match.animator_a.name,

                    "animator_b": match.animator_b.name,

                    "votes_a": match.votes_a,

                    "votes_b": match.votes_b,

                    "winner": None,

                    "loser": None,
                })

        return result
