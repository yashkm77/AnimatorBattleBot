from dataclasses import dataclass
from typing import Optional
import random


# ============================================================
# ANIMATOR
# ============================================================

@dataclass
class Animator:

    name: str

    # Last successful Sakugabooru clip.
    # Used as a fallback if another clip cannot be found.
    current_clip: Optional[dict] = None

    wins: int = 0
    losses: int = 0
    battles: int = 0

    # Sakugabooru quality / popularity.
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
    #
    # Round 1
    # Round 2
    # Round 3
    # Final
    #
    bracket is assigned automatically.
    bracket: str = "Round 1"

    votes_a: int = 0
    votes_b: int = 0

    winner: Optional[Animator] = None
    loser: Optional[Animator] = None

    completed: bool = False

    # --------------------------------------------------------
    # SET RESULT
    # --------------------------------------------------------

    def set_result(
        self,
        winner: Animator,
    ):

        if self.completed:

            raise ValueError(
                "This match is already complete."
            )

        if winner not in (
            self.animator_a,
            self.animator_b,
        ):

            raise ValueError(
                "Winner must be one of the "
                "match participants."
            )

        # ----------------------------------------------------
        # WINNER
        # ----------------------------------------------------

        self.winner = winner

        # ----------------------------------------------------
        # LOSER
        # ----------------------------------------------------

        if winner is self.animator_a:

            self.loser = self.animator_b

        else:

            self.loser = self.animator_a

        # ----------------------------------------------------
        # STATISTICS
        # ----------------------------------------------------

        self.animator_a.battles += 1

        self.animator_b.battles += 1

        winner.wins += 1

        if self.loser is not None:

            self.loser.losses += 1

        self.completed = True


# ============================================================
# ANIMATOR BATTLE
# ============================================================

class AnimatorBattle:

    """
    Single-elimination animator tournament.

    rounds = 1
        2 animators
        1 match
        1 champion

    rounds = 2
        4 animators
        2 Round 1 matches
        1 Final

    rounds = 3
        8 animators
        4 Round 1 matches
        2 Round 2 matches
        1 Final

    rounds = 4
        16 animators
        8 Round 1 matches
        4 Round 2 matches
        2 Round 3 matches
        1 Final

    Required animators:

        2 ** rounds

    There is NO losers bracket.

    Once an animator loses,
    they are permanently eliminated.
    """

    # ========================================================
    # INIT
    # ========================================================

    def __init__(
        self,
        animators: list[Animator],
        rounds: int = 1,
        mode: str = "random",
    ):

        # ----------------------------------------------------
        # VALIDATE ANIMATORS
        # ----------------------------------------------------

        if not animators:

            raise ValueError(
                "At least 2 animators are required."
            )

        # ----------------------------------------------------
        # VALIDATE ROUNDS
        # ----------------------------------------------------

        if rounds < 1:

            raise ValueError(
                "Rounds must be at least 1."
            )

        if rounds > 10:

            raise ValueError(
                "Rounds cannot be greater than 10."
            )

        # ----------------------------------------------------
        # VALIDATE MODE
        # ----------------------------------------------------

        if mode not in (
            "random",
            "continuous",
        ):

            raise ValueError(
                "Mode must be 'random' or 'continuous'."
            )

        # ----------------------------------------------------
        # REQUIRED PARTICIPANTS
        # ----------------------------------------------------

        required_animators = 2 ** rounds

        if len(animators) != required_animators:

            raise ValueError(
                f"{rounds} rounds requires exactly "
                f"{required_animators} animators."
            )

        # ----------------------------------------------------
        # STORE
        # ----------------------------------------------------

        self.animators = list(animators)

        self.rounds = rounds

        self.mode = mode

        # ----------------------------------------------------
        # TOURNAMENT STATE
        # ----------------------------------------------------

        self.current_round = 0

        self.match_counter = 0

        self.phase = "Not Started"

        self.current_match: Optional[Match] = None

        # Matches waiting to be played.
        self.match_queue: list[Match] = []

        # Completed matches.
        self.completed_matches: list[Match] = []

        # Winners from the current round.
        self.winners: list[Animator] = []

        # Eliminated animators.
        self.eliminated: list[Animator] = []

        # Participants in the current round.
        self.current_participants: list[Animator] = []

        # Tournament champion.
        self.champion: Optional[Animator] = None

        # Stop flag.
        self.stopped = False

        # Start flag.
        self.started = False

    # ========================================================
    # REQUIRED ANIMATORS
    # ========================================================

    @property
    def required_animators(self):

        return 2 ** self.rounds

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
        bracket: Optional[str] = None,
    ):

        if self.stopped:

            return None

        # ----------------------------------------------------
        # AUTOMATIC BRACKET NAME
        # ----------------------------------------------------

        if bracket is None:

            if self.current_round == self.rounds:

                bracket = "Final"

            else:

                bracket = (
                    f"Round {self.current_round}"
                )

        # ----------------------------------------------------
        # CREATE
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # ALREADY STOPPED
        # ----------------------------------------------------

        if self.stopped:

            return []

        # ----------------------------------------------------
        # ALREADY STARTED
        # ----------------------------------------------------

        if self.started:

            return self.get_pending_matches()

        # ----------------------------------------------------
        # INITIALIZE
        # ----------------------------------------------------

        self.started = True

        self.current_round = 1

        self.phase = (
            f"Round {self.current_round}"
        )

        # ----------------------------------------------------
        # SHUFFLE PARTICIPANTS
        # ----------------------------------------------------

        participants = self.animators.copy()

        random.shuffle(
            participants
        )

        self.current_participants = (
            participants.copy()
        )

        # ----------------------------------------------------
        # CLEAR STATE
        # ----------------------------------------------------

        self.winners.clear()

        self.eliminated.clear()

        self.match_queue.clear()

        self.completed_matches.clear()

        self.current_match = None

        self.champion = None

        # ----------------------------------------------------
        # BUILD ROUND 1
        # ----------------------------------------------------

        self.build_round_matches(
            participants
        )

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

        # ----------------------------------------------------
        # RESET CURRENT ROUND WINNERS
        # ----------------------------------------------------

        self.winners.clear()

        # ----------------------------------------------------
        # COPY
        # ----------------------------------------------------

        participants = participants.copy()

        # Shuffle only when building the round.
        random.shuffle(
            participants
        )

        self.current_participants = (
            participants.copy()
        )

        matches = []

        # ----------------------------------------------------
        # CREATE MATCHES
        # ----------------------------------------------------

        while len(participants) >= 2:

            animator_a = participants.pop(0)

            animator_b = participants.pop(0)

            if self.current_round == self.rounds:

                bracket = "Final"

            else:

                bracket = (
                    f"Round {self.current_round}"
                )

            match = self.create_match(
                animator_a,
                animator_b,
                bracket,
            )

            if match is not None:

                matches.append(
                    match
                )

                self.match_queue.append(
                    match
                )

        # ----------------------------------------------------
        # PHASE
        # ----------------------------------------------------

        if self.current_round == self.rounds:

            self.phase = "Final"

        else:

            self.phase = (
                f"Round {self.current_round}"
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

        # ----------------------------------------------------
        # ACTIVE MATCH
        # ----------------------------------------------------

        if self.current_match is not None:

            return self.current_match

        # ----------------------------------------------------
        # NO QUEUED MATCHES
        # ----------------------------------------------------

        if not self.match_queue:

            return None

        # ----------------------------------------------------
        # POP NEXT MATCH
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # STOPPED
        # ----------------------------------------------------

        if self.stopped:

            return False

        # ----------------------------------------------------
        # ALREADY COMPLETE
        # ----------------------------------------------------

        if match.completed:

            return False

        # ----------------------------------------------------
        # VERIFY ACTIVE MATCH
        # ----------------------------------------------------

        if self.current_match is not None:

            if (
                match.match_id
                != self.current_match.match_id
            ):

                raise ValueError(
                    "This is not the current battle match."
                )

        # ----------------------------------------------------
        # VERIFY WINNER
        # ----------------------------------------------------

        if winner not in (
            match.animator_a,
            match.animator_b,
        ):

            raise ValueError(
                "Winner is not part of this match."
            )

        # ----------------------------------------------------
        # SET RESULT
        # ----------------------------------------------------

        match.set_result(
            winner
        )

        # ----------------------------------------------------
        # LOSER
        # ----------------------------------------------------

        loser = match.loser

        if loser is None:

            raise RuntimeError(
                "Match has no loser."
            )

        # ----------------------------------------------------
        # SAVE COMPLETED MATCH
        # ----------------------------------------------------

        self.completed_matches.append(
            match
        )

        # ----------------------------------------------------
        # WINNER ADVANCES
        # ----------------------------------------------------

        self.winners.append(
            winner
        )

        # ----------------------------------------------------
        # ELIMINATE LOSER
        # ----------------------------------------------------

        self.eliminate(
            loser
        )

        # ----------------------------------------------------
        # CLEAR ACTIVE MATCH
        # ----------------------------------------------------

        self.current_match = None

        # ----------------------------------------------------
        # CURRENT ROUND COMPLETE?
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

        # ----------------------------------------------------
        # DON'T ADVANCE WHILE MATCHES REMAIN
        # ----------------------------------------------------

        if self.match_queue:

            return

        # ----------------------------------------------------
        # CHAMPION
        # ----------------------------------------------------

        if len(self.winners) == 1:

            self.champion = (
                self.winners[0]
            )

            self.phase = "Finished"

            return

        # ----------------------------------------------------
        # SAFETY CHECK
        # ----------------------------------------------------

        if len(self.winners) < 2:

            self.phase = "Finished"

            return

        # ----------------------------------------------------
        # ADVANCE ROUND
        # ----------------------------------------------------

        self.current_round += 1

        # ----------------------------------------------------
        # SAFETY
        # ----------------------------------------------------

        if self.current_round > self.rounds:

            self.champion = (
                self.winners[0]
            )

            self.phase = "Finished"

            return

        # ----------------------------------------------------
        # NEXT ROUND PARTICIPANTS
        # ----------------------------------------------------

        participants = (
            self.winners.copy()
        )

        # ----------------------------------------------------
        # BUILD NEXT ROUND
        # ----------------------------------------------------

        self.build_round_matches(
            participants
        )

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

        # Reset animator statistics.
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

            "animators": len(
                self.animators
            ),

            "required_animators": (
                self.required_animators
            ),

            "completed_matches": len(
                self.completed_matches
            ),

            "pending_matches": len(
                self.match_queue
            ),

            "active_match": (
                self.current_match.match_id
                if self.current_match
                else None
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

            "started": self.started,
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

            "completed": match.completed,
        }

    # ========================================================
    # BRACKET
    # ========================================================

    def bracket(self):

        """
        Return a simple tournament bracket summary.

        Completed matches include their winner/loser.

        Pending and active matches have no result yet.
        """

        result = []

        # ----------------------------------------------------
        # COMPLETED MATCHES
        # ----------------------------------------------------

        for match in self.completed_matches:

            result.append(
                {
                    "match_id": match.match_id,

                    "round": match.bracket,

                    "animator_a": (
                        match.animator_a.name
                    ),

                    "animator_b": (
                        match.animator_b.name
                    ),

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

                    "completed": True,
                }
            )

        # ----------------------------------------------------
        # PENDING MATCHES
        # ----------------------------------------------------

        for match in self.match_queue:

            result.append(
                {
                    "match_id": match.match_id,

                    "round": match.bracket,

                    "animator_a": (
                        match.animator_a.name
                    ),

                    "animator_b": (
                        match.animator_b.name
                    ),

                    "votes_a": match.votes_a,

                    "votes_b": match.votes_b,

                    "winner": None,

                    "loser": None,

                    "completed": False,
                }
            )

        # ----------------------------------------------------
        # ACTIVE MATCH
        # ----------------------------------------------------

        if self.current_match is not None:

            match = self.current_match

            # The active match has already been removed
            # from match_queue, so add it separately.
            result.append(
                {
                    "match_id": match.match_id,

                    "round": match.bracket,

                    "animator_a": (
                        match.animator_a.name
                    ),

                    "animator_b": (
                        match.animator_b.name
                    ),

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

                    "completed": match.completed,
                }
            )

        return result