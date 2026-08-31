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

def display_name(name: str) -> str:

    return (
        str(name)
        .replace("_", " ")
        .strip()
    )


# ============================================================
# VOTING VIEW
# ============================================================

class BattleVoteView(discord.ui.View):

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
        label="Vote",
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

        self.voter_choices[user_id] = (
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
        label="Vote",
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

        self.voter_choices[user_id] = (
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
    # INACTIVITY LIMIT
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

            total_time = (
                now - start_time
            )

            if total_time >= VOTE_TIME:
                break

            if not self.voter_choices:

                remaining = (
                    VOTE_TIME
                    - total_time
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
                    VOTE_TIME
                    - total_time
                )

            else:

                last_vote = (
                    self.last_vote_time
                    or start_time
                )

                inactivity = (
                    now - last_vote
                )

                if (
                    inactivity
                    >= inactivity_limit
                ):
                    break

                inactivity_remaining = (
                    inactivity_limit
                    - inactivity
                )

                total_remaining = (
                    VOTE_TIME
                    - total_time
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

    return clip_a, clip_b


# ============================================================
# RUN ONE MATCH
# ============================================================

async def run_match(
    interaction,
    tournament,
    sakuga,
    match,
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

    clip_a, clip_b = await get_clips_for_match(
        sakuga,
        match.animator_a,
        match.animator_b,
        tournament.mode,
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
    # VIEW
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

    match_number = match.match_id

    await interaction.channel.send(
        f"⚔️ **ANIMATOR BATTLE — MATCH "
        f"{match_number}/{tournament.rounds}**"
    )

    # ========================================================
    # IMPORTANT:
    #
    # We do NOT reveal the anime.
    #
    # We also don't need to send the animator name beside
    # the clip if the purpose is to vote on the clips.
    # The buttons already identify the animator.
    # ========================================================

    await interaction.channel.send(
        "🎬 **CLIP A**"
    )

    await interaction.channel.send(
        clip_a["url"]
    )

    await interaction.channel.send(
        "🎬 **CLIP B**"
    )

    await interaction.channel.send(
        clip_b["url"]
    )

    # ========================================================
    # VOTING
    # ========================================================

    await interaction.channel.send(
        f"🗳️ **Vote for the better clip!**\n"
        f"⏱️ **{VOTE_TIME} seconds**\n\n"
        f"**A:** {name_a}\n"
        f"**B:** {name_b}"
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

        tie = True

    elif votes_a > votes_b:

        winner = match.animator_a

        tie = False

    else:

        winner = match.animator_b

        tie = False

    # ========================================================
    # RECORD
    # ========================================================

    tournament.record_result(
        match,
        winner,
    )

    # ========================================================
    # RESULT
    # ========================================================

    winner_name = display_name(
        winner.name
    )

    if tie:

        result_text = (
            f"⚖️ **It's a tie!**\n"
            f"🎲 Randomly selected winner: "
            f"**{winner_name}**"
        )

    else:

        result_text = (
            f"🏆 **{winner_name} wins!**"
        )

    await interaction.channel.send(
        result_text
    )

    # ========================================================
    # SCORE
    # ========================================================

    await interaction.channel.send(
        f"🗳️ **Final votes**\n"
        f"• **{name_a}:** {votes_a}\n"
        f"• **{name_b}:** {votes_b}"
    )

    # ========================================================
    # REVEAL ANIME
    # ========================================================

    anime_a = await sakuga.find_anime_from_clip(
        clip_a
    )

    anime_b = await sakuga.find_anime_from_clip(
        clip_b
    )

    reveal_lines = []

    if anime_a:

        reveal_lines.append(
            f"🎞️ **{name_a}:** {anime_a}"
        )

    if anime_b:

        reveal_lines.append(
            f"🎞️ **{name_b}:** {anime_b}"
        )

    if reveal_lines:

        await interaction.channel.send(
            "🔓 **Match information revealed**\n"
            + "\n".join(reveal_lines)
        )

    else:

        await interaction.channel.send(
            "🔓 **Match information revealed**\n"
            "Anime information wasn't available."
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
# RUN BATTLE
# ============================================================

async def run_tournament(
    interaction,
    tournament,
    sakuga,
):

    matches = tournament.start()

    # ========================================================
    # EXACT NUMBER OF MATCHES
    # ========================================================

    while matches:

        if tournament.stopped:
            return

        for match in matches:

            if tournament.stopped:
                return

            success = await run_match(
                interaction,
                tournament,
                sakuga,
                match,
            )

            if not success:
                return

            if tournament.stopped:
                return

            await asyncio.sleep(1)

        # ----------------------------------------------------
        # Important:
        #
        # record_result() does NOT generate another bracket.
        # next_matches() only returns anything that was already
        # queued.
        # ----------------------------------------------------

        matches = tournament.next_matches()

    # ========================================================
    # FINISHED
    # ========================================================

    if tournament.is_finished():

        await interaction.channel.send(
            f"🏁 **ANIMATOR BATTLE FINISHED!**\n\n"
            f"Completed **{tournament.completed_match_count}"
            f"/{tournament.rounds} matches**."
        )


# ============================================================
# /BATTLE
# ============================================================

@bot.tree.command(
    name="battle",
    description="Start an animator battle.",
)
@app_commands.describe(
    rounds="Number of matches (1-16)",
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
    rounds: app_commands.Range[int, 1, 16],
    mode: app_commands.Choice[str],
):

    guild_id = interaction.guild_id

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
    # IMPORTANT:
    #
    # We need TWO UNIQUE ANIMATORS PER MATCH.
    #
    # 2 rounds = 4 animators
    # 4 rounds = 8 animators
    # etc.
    # ========================================================

    animator_count = rounds * 2

    sakuga = SakugabooruClient()

    # ========================================================
    # START SEARCH
    # ========================================================

    await interaction.response.send_message(
        "🔎 **Searching the animator database "
        "and Sakugabooru...**"
    )

    # ========================================================
    # GET POPULAR/VERIFIED ANIMATORS
    # ========================================================

    try:

        candidates = await sakuga.choose_battle_animators(
            animator_count
        )

    except Exception as e:

        print(
            f"Animator selection error: {e}"
        )

        await interaction.channel.send(
            "❌ Failed to select animators."
        )

        sakuga.reset()

        return

    # ========================================================
    # NOT ENOUGH
    # ========================================================

    if len(candidates) < animator_count:

        await interaction.channel.send(
            f"❌ I could only find "
            f"**{len(candidates)}** verified animators "
            f"with usable Sakugabooru clips.\n\n"
            f"**{animator_count}** are required for "
            f"**{rounds} matches**."
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
                    "quality",
                    0,
                )
            ),
        )

        animators.append(
            animator
        )

    # ========================================================
    # CREATE BATTLE
    # ========================================================

    tournament = AnimatorBattle(
        animators,
        mode=mode.value,
        rounds=rounds,
    )

    bot.active_battles[
        guild_id
    ] = tournament

    # ========================================================
    # PARTICIPANTS
    # ========================================================

    participant_lines = "\n".join(
        f"• **{display_name(a.name)}**"
        for a in animators
    )

    await interaction.channel.send(
        f"👥 **Battle participants**\n"
        f"{participant_lines}"
    )

    # ========================================================
    # STARTING MESSAGE
    # ========================================================

    await interaction.channel.send(
        "⚔️ **ANIMATOR BATTLE STARTING!**\n\n"
        f"🎯 **{rounds} matches**\n"
        f"👥 **{animator_count} animators**\n"
        f"🎬 **{mode.name}**\n"
        f"⏱️ **{VOTE_TIME} seconds per match**\n\n"
        "Anime information will be revealed "
        "**after each match**."
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
            "the animator battle.\n"
            f"```{e}```"
        )

    finally:

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
        "      ANIMATOR BATTLE BOT"
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