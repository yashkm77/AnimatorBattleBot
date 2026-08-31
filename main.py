import asyncio
import random
import discord

from discord import app_commands
from discord.ext import commands

from config import DISCORD_TOKEN
from battle import Animator, AnimatorBattle
from sakugabooru import SakugabooruClient


# ============================================================
# SETTINGS
# ============================================================

VOTE_TIME = 60

EARLY_END_1_VOTE = 20
EARLY_END_2_3_VOTES = 30


# ============================================================
# BOT
# ============================================================

class AnimatorBattleBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.active_battles = {}

    async def setup_hook(self):

        await self.tree.sync()

        print(
            "Slash commands synced."
        )


bot = AnimatorBattleBot()


# ============================================================
# DISPLAY NAME
# ============================================================

def display_name(
    name: str,
):

    if not isinstance(
        name,
        str,
    ):
        return "Unknown Animator"

    return (
        name
        .replace("_", " ")
        .strip()
    )


# ============================================================
# VOTING VIEW
# ============================================================

class BattleVoteView(
    discord.ui.View
):

    def __init__(
        self,
        animator_a,
        animator_b,
    ):

        super().__init__(
            timeout=VOTE_TIME
        )

        self.animator_a = animator_a
        self.animator_b = animator_b

        self.votes_a = set()
        self.votes_b = set()

        self.voter_choices = {}

        self.last_vote_time = None

        self.vote_event = asyncio.Event()

    # ========================================================
    # VOTE A
    # ========================================================

    @discord.ui.button(
        label="Vote A",
        style=discord.ButtonStyle.primary,
    )
    async def vote_a(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        user_id = interaction.user.id

        self.votes_b.discard(
            user_id
        )

        self.votes_a.add(
            user_id
        )

        self.voter_choices[
            user_id
        ] = (
            interaction.user.display_name,
            self.animator_a.name,
        )

        self.last_vote_time = (
            asyncio.get_running_loop().time()
        )

        self.vote_event.set()

        self.vote_event.clear()

        await interaction.response.send_message(
            f"✅ Your vote is for "
            f"**{display_name(self.animator_a.name)}**.",
            ephemeral=True,
        )

    # ========================================================
    # VOTE B
    # ========================================================

    @discord.ui.button(
        label="Vote B",
        style=discord.ButtonStyle.secondary,
    )
    async def vote_b(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        user_id = interaction.user.id

        self.votes_a.discard(
            user_id
        )

        self.votes_b.add(
            user_id
        )

        self.voter_choices[
            user_id
        ] = (
            interaction.user.display_name,
            self.animator_b.name,
        )

        self.last_vote_time = (
            asyncio.get_running_loop().time()
        )

        self.vote_event.set()

        self.vote_event.clear()

        await interaction.response.send_message(
            f"✅ Your vote is for "
            f"**{display_name(self.animator_b.name)}**.",
            ephemeral=True,
        )

    # ========================================================
    # DISABLE BUTTONS
    # ========================================================

    def disable_buttons(self):

        for child in self.children:

            child.disabled = True

    # ========================================================
    # INACTIVITY
    # ========================================================

    def get_inactivity_limit(self):

        total_votes = (
            len(self.votes_a)
            + len(self.votes_b)
        )

        if total_votes <= 1:
            return EARLY_END_1_VOTE

        if total_votes <= 3:
            return EARLY_END_2_3_VOTES

        return None

    # ========================================================
    # WAIT
    # ========================================================

    async def wait_for_votes(self):

        start_time = (
            asyncio.get_running_loop().time()
        )

        while True:

            now = (
                asyncio.get_running_loop().time()
            )

            elapsed = (
                now - start_time
            )

            if elapsed >= VOTE_TIME:
                break

            if not self.voter_choices:

                remaining = (
                    VOTE_TIME - elapsed
                )

                try:

                    await asyncio.wait_for(
                        self.vote_event.wait(),
                        timeout=remaining,
                    )

                except asyncio.TimeoutError:

                    break

                continue

            inactivity_limit = (
                self.get_inactivity_limit()
            )

            if inactivity_limit is None:

                remaining = (
                    VOTE_TIME - elapsed
                )

            else:

                last_vote = (
                    self.last_vote_time
                    or start_time
                )

                inactivity = (
                    now - last_vote
                )

                if inactivity >= inactivity_limit:
                    break

                inactivity_remaining = (
                    inactivity_limit
                    - inactivity
                )

                total_remaining = (
                    VOTE_TIME
                    - elapsed
                )

                remaining = min(
                    inactivity_remaining,
                    total_remaining,
                )

            try:

                await asyncio.wait_for(
                    self.vote_event.wait(),
                    timeout=remaining,
                )

            except asyncio.TimeoutError:

                break

        self.disable_buttons()


# ============================================================
# GET CLIPS
# ============================================================

async def get_clips_for_match(
    sakuga,
    animator_a,
    animator_b,
    mode,
):

    clip_a = await sakuga.get_battle_clip(
        animator_a.name,
        mode,
    )

    clip_b = await sakuga.get_battle_clip(
        animator_b.name,
        mode,
    )

    return (
        clip_a,
        clip_b,
    )


# ============================================================
# RUN MATCH
# ============================================================

async def run_match(
    interaction,
    tournament,
    sakuga,
    match,
    match_number,
):

    name_a = display_name(
        match.animator_a.name
    )

    name_b = display_name(
        match.animator_b.name
    )

    # ========================================================
    # GET CLIPS
    # ========================================================

    clip_a, clip_b = (
        await get_clips_for_match(
            sakuga,
            match.animator_a,
            match.animator_b,
            tournament.mode,
        )
    )

    if clip_a is None:

        await interaction.channel.send(
            f"❌ Couldn't find a Sakugabooru "
            f"clip for **{name_a}**."
        )

        return False

    if clip_b is None:

        await interaction.channel.send(
            f"❌ Couldn't find a Sakugabooru "
            f"clip for **{name_b}**."
        )

        return False

    # ========================================================
    # SAVE CURRENT CLIPS
    # ========================================================

    match.animator_a.current_clip = clip_a
    match.animator_b.current_clip = clip_b

    # ========================================================
    # VOTE VIEW
    # ========================================================

    view = BattleVoteView(
        match.animator_a,
        match.animator_b,
    )

    view.children[0].label = name_a
    view.children[1].label = name_b

    # ========================================================
    # HEADER
    # ========================================================

    await interaction.channel.send(
        f"⚔️ **ANIMATOR BATTLE — MATCH "
        f"{match_number}**\n"
        f"**{name_a} vs {name_b}**"
    )

    # ========================================================
    # CLIP A
    # ========================================================

    await interaction.channel.send(
        f"🎬 **{name_a}**"
    )

    await interaction.channel.send(
        clip_a["url"]
    )

    # ========================================================
    # CLIP B
    # ========================================================

    await interaction.channel.send(
        f"🎬 **{name_b}**"
    )

    await interaction.channel.send(
        clip_b["url"]
    )

    # ========================================================
    # VOTING
    # ========================================================

    await interaction.channel.send(
        f"🗳️ **Vote for the better clip!**\n"
        f"⏱️ **{VOTE_TIME} seconds**"
    )

    await interaction.channel.send(
        " ",
        view=view,
    )

    # ========================================================
    # WAIT
    # ========================================================

    await view.wait_for_votes()

    # ========================================================
    # COUNT
    # ========================================================

    votes_a = len(
        view.votes_a
    )

    votes_b = len(
        view.votes_b
    )

    match.votes_a = votes_a
    match.votes_b = votes_b

    # ========================================================
    # WINNER
    # ========================================================

    if votes_a == votes_b:

        winner = random.choice(
            [
                match.animator_a,
                match.animator_b,
            ]
        )

        tie_message = (
            "🤝 **Tie! Random winner selected.**"
        )

    elif votes_a > votes_b:

        winner = match.animator_a

        tie_message = None

    else:

        winner = match.animator_b

        tie_message = None

    # ========================================================
    # RECORD RESULT
    # ========================================================

    try:

        tournament.record_result(
            match,
            winner,
        )

    except Exception as e:

        print(
            f"Failed to record battle result: {e}"
        )

        await interaction.channel.send(
            "❌ Failed to record the match result."
        )

        return False

    # ========================================================
    # RESULT
    # ========================================================

    winner_name = display_name(
        winner.name
    )

    result_text = (
        f"🏆 **{winner_name} wins!**\n\n"
        f"**{name_a}** — {votes_a} vote(s)\n"
        f"**{name_b}** — {votes_b} vote(s)"
    )

    if tie_message:

        result_text = (
            tie_message
            + "\n\n"
            + result_text
        )

    await interaction.channel.send(
        result_text
    )

    # ========================================================
    # VOTERS
    # ========================================================

    if view.voter_choices:

        voter_lines = []

        for (
            username,
            voted_for,
        ) in view.voter_choices.values():

            voter_lines.append(
                f"• **{username}** → "
                f"**{display_name(voted_for)}**"
            )

        await interaction.channel.send(
            "🗳️ **Votes**\n\n"
            + "\n".join(
                voter_lines
            )
        )

    else:

        await interaction.channel.send(
            "🗳️ **No votes were cast.**"
        )

    return True


# ============================================================
# RUN TOURNAMENT
# ============================================================

async def run_tournament(
    interaction,
    tournament,
    sakuga,
):

    # --------------------------------------------------------
    # Start.
    # --------------------------------------------------------

    matches = tournament.start()

    while matches:

        if tournament.stopped:
            return

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # We use the exact list returned for this round.
        # Results create the NEXT round only after every
        # current match has completed.
        # ----------------------------------------------------

        for match in matches:

            if tournament.stopped:
                return

            success = await run_match(
                interaction,
                tournament,
                sakuga,
                match,
                match.match_id,
            )

            if not success:
                return

            if tournament.stopped:
                return

            await asyncio.sleep(1)

        # ----------------------------------------------------
        # Champion check BEFORE requesting another round.
        # ----------------------------------------------------

        if tournament.is_finished():

            break

        # ----------------------------------------------------
        # Get next round.
        # ----------------------------------------------------

        matches = tournament.next_matches()

    # ========================================================
    # CHAMPION
    # ========================================================

    if tournament.champion:

        champion_name = display_name(
            tournament.champion.name
        )

        await interaction.channel.send(
            f"🏆 **ANIMATOR BATTLE CHAMPION**\n\n"
            f"## 🏆 {champion_name}\n\n"
            f"Congratulations!"
        )


# ============================================================
# /BATTLE
# ============================================================

@bot.tree.command(
    name="battle",
    description="Start an animator battle.",
)
@app_commands.describe(
    rounds="Number of animators (2, 4, 8 or 16)",
    mode="Clip mode",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(
            name="Random Clips",
            value="random",
        ),
        app_commands.Choice(
            name="Continuous Clip",
            value="continuous",
        ),
    ]
)
async def battle_command(
    interaction: discord.Interaction,
    rounds: app_commands.Range[int, 2, 16],
    mode: app_commands.Choice[str],
):

    guild_id = interaction.guild_id

    # ========================================================
    # VALIDATE SIZE
    # ========================================================

    if rounds not in (
        2,
        4,
        8,
        16,
    ):

        await interaction.response.send_message(
            "❌ Choose **2, 4, 8, or 16** animators.",
            ephemeral=True,
        )

        return

    # ========================================================
    # ACTIVE BATTLE
    # ========================================================

    if guild_id in bot.active_battles:

        await interaction.response.send_message(
            "⚠️ There is already an animator "
            "battle running in this server.",
            ephemeral=True,
        )

        return

    # ========================================================
    # CREATE CLIENT
    # ========================================================

    sakuga = SakugabooruClient()

    # ========================================================
    # RESPONSE
    # ========================================================

    await interaction.response.send_message(
        "🔎 **Finding popular animators on "
        "Sakugabooru...**"
    )

    # ========================================================
    # CHOOSE PARTICIPANTS
    # ========================================================

    try:

        candidates = (
            await sakuga.choose_battle_animators(
                rounds
            )
        )

    except Exception as e:

        print(
            f"Animator selection error: {e}"
        )

        await interaction.channel.send(
            "❌ Failed to find animators "
            "from Sakugabooru."
        )

        sakuga.reset()

        return

    # ========================================================
    # NOT ENOUGH
    # ========================================================

    if len(candidates) < rounds:

        await interaction.channel.send(
            f"❌ I could only find "
            f"**{len(candidates)}** verified "
            f"animators with usable video clips, "
            f"but the battle needs **{rounds}**."
        )

        sakuga.reset()

        return

    # ========================================================
    # CREATE ANIMATORS
    # ========================================================

    animators = []

    for candidate in candidates:

        animator = Animator(
            name=candidate["name"],
            popularity=float(
                candidate.get(
                    "popularity",
                    candidate.get(
                        "quality",
                        0,
                    ),
                )
            ),
        )

        animators.append(
            animator
        )

    # ========================================================
    # TOURNAMENT
    # ========================================================

    tournament = AnimatorBattle(
        animators,
        mode=mode.value,
    )

    bot.active_battles[
        guild_id
    ] = tournament

    # ========================================================
    # PARTICIPANTS
    #
    # IMPORTANT:
    # ONLY animator names are displayed.
    #
    # No anime title.
    # No Sakugabooru tag.
    # No clip.
    # ========================================================

    participant_lines = "\n".join(
        f"• **{display_name(animator.name)}**"
        for animator in animators
    )

    await interaction.channel.send(
        "👥 **Battle participants**\n\n"
        + participant_lines
    )

    # ========================================================
    # START MESSAGE
    # ========================================================

    await interaction.channel.send(
        "⚔️ **ANIMATOR BATTLE STARTING!**\n\n"
        f"👥 **{rounds} animators**\n"
        f"🎬 **{mode.name}**\n"
        f"⏱️ **{VOTE_TIME} seconds per match**\n\n"
        "Get ready..."
    )

    # ========================================================
    # RUN
    # ========================================================

    try:

        await asyncio.sleep(2)

        await run_tournament(
            interaction,
            tournament,
            sakuga,
        )

    except Exception as e:

        print(
            f"Battle error: {e}"
        )

        await interaction.channel.send(
            "❌ Something went wrong during "
            "the animator battle."
        )

        print(
            repr(e)
        )

    finally:

        tournament.stop()

        sakuga.reset()

        bot.active_battles.pop(
            guild_id,
            None,
        )


# ============================================================
# /STOP
# ============================================================

@bot.tree.command(
    name="stop",
    description="Completely stop the current animator battle.",
)
async def stop_command(
    interaction: discord.Interaction,
):

    guild_id = interaction.guild_id

    tournament = bot.active_battles.get(
        guild_id
    )

    if tournament is None:

        await interaction.response.send_message(
            "❌ There is no animator battle "
            "running in this server.",
            ephemeral=True,
        )

        return

    tournament.stop()

    bot.active_battles.pop(
        guild_id,
        None,
    )

    await interaction.response.send_message(
        "🛑 **Animator Battle completely stopped.**"
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print()
    print(
        "========================================"
    )
    print(
        "        ANIMATOR BATTLE BOT"
    )
    print(
        "========================================"
    )
    print(
        f"Logged in as {bot.user}"
    )
    print(
        f"Bot ID: {bot.user.id}"
    )
    print(
        "========================================"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    bot.run(
        DISCORD_TOKEN
    )