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
) -> str:

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
    # DISABLE
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

            total_time = (
                now - start_time
            )

            if total_time >= VOTE_TIME:

                break

            if not self.voter_choices:

                remaining = (
                    VOTE_TIME - total_time
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
                    VOTE_TIME - total_time
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
                    VOTE_TIME - total_time
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
# RUN MATCH — CLEAN DISPLAY
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

    # ========================================================
    # CLIP FALLBACK
    # ========================================================

    if clip_a is None and clip_b is None:

        await interaction.channel.send(
            f"❌ Couldn't find usable clips for "
            f"**{name_a}** or **{name_b}**."
        )

        return False

    # If one animator has no new clip,
    # try using that animator's previous clip.
    if clip_a is None:

        fallback_clip = getattr(
            match.animator_a,
            "current_clip",
            None,
        )

        if fallback_clip is not None:

            clip_a = fallback_clip

        else:

            await interaction.channel.send(
                f"❌ Couldn't find a Sakugabooru "
                f"clip for **{name_a}**."
            )

            return False

    if clip_b is None:

        fallback_clip = getattr(
            match.animator_b,
            "current_clip",
            None,
        )

        if fallback_clip is not None:

            clip_b = fallback_clip

        else:

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
    # VOTING VIEW
    # ========================================================

    view = BattleVoteView(
        match.animator_a,
        match.animator_b,
    )

    view.children[0].label = name_a
    view.children[1].label = name_b

    # ========================================================
    # MATCH HEADER
    # ========================================================

    await interaction.channel.send(
        f"⚔️ **ANIMATOR BATTLE — MATCH {match.match_id}**\n"
        f"**{name_a} vs {name_b}**"
    )

    # ========================================================
    # CLIP A
    # ========================================================

    await interaction.channel.send(
        f"🎬 **{name_a}**\n"
        f"{clip_a['url']}"
    )

    # ========================================================
    # CLIP B
    # ========================================================

    await interaction.channel.send(
        f"🎬 **{name_b}**\n"
        f"{clip_b['url']}"
    )

    # ========================================================
    # VOTING
    # ========================================================

    await interaction.channel.send(
        f"🗳️ **Vote for the best animation!**\n"
        f"⏱️ **{VOTE_TIME} seconds**",
        view=view,
    )

    # ========================================================
    # WAIT FOR VOTES
    # ========================================================

    await view.wait_for_votes()

    # ========================================================
    # COUNT VOTES
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
    # DETERMINE WINNER
    # ========================================================

    if votes_a == votes_b:

        winner = random.choice(
            [
                match.animator_a,
                match.animator_b,
            ]
        )

    elif votes_a > votes_b:

        winner = match.animator_a

    else:

        winner = match.animator_b

    # ========================================================
    # RECORD RESULT
    # ========================================================

    tournament.record_result(
        match,
        winner,
    )

    # ========================================================
    # RESULT MESSAGE
    # ========================================================

    winner_name = display_name(
        winner.name
    )

    loser_name = display_name(
        match.loser.name
    )

    result_lines = [
        f"🏆 **{winner_name} wins!**",
        "",
        f"🗳️ **Votes: {name_a} {votes_a} — "
        f"{name_b} {votes_b}**",
    ]

    # ========================================================
    # VOTER LIST
    # ========================================================

    if view.voter_choices:

        result_lines.append("")

        for (
            username,
            voted_for,
        ) in view.voter_choices.values():

            result_lines.append(
                f"👤 **{username}** → "
                f"**{display_name(voted_for)}**"
            )

    else:

        result_lines.append("")
        result_lines.append(
            "👤 **No votes were cast.**"
        )

    await interaction.channel.send(
        "\n".join(result_lines)
    )

    # ========================================================
    # NO SEPARATOR
    # ========================================================
    #
    # The next match starts naturally.
    #
    # No:
    #
    # ──────────────
    #
    # ========================================================

    return True


# ============================================================
# RUN TOURNAMENT
# ============================================================

async def run_tournament(
    interaction,
    tournament,
    sakuga,
):

    tournament.start()

    # IMPORTANT:
    #
    # Do NOT use:
    #
    # matches = tournament.start()
    # for match in matches
    #
    # because that leaves matches inside the queue.
    #
    # Instead get_next_match() removes each match from
    # the queue before it starts.

    while not tournament.stopped:

        match = tournament.get_next_match()

        if match is None:

            if tournament.is_finished():

                break

            # A new round may be generated after
            # record_result().
            await asyncio.sleep(0.2)

            continue

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

    # ========================================================
    # CHAMPION
    # ========================================================

    if (
        tournament.champion
        and not tournament.stopped
    ):

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
    description="Start a single-elimination animator tournament.",
)
@app_commands.describe(
    rounds="Tournament rounds: 1=2 animators, 2=4, 3=8, 4=16",
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
    rounds: app_commands.Range[int, 1, 4],
    mode: app_commands.Choice[str],
):

    guild_id = interaction.guild_id

    # ========================================================
    # CALCULATE TOURNAMENT SIZE
    # ========================================================

    # 1 round  = 2 animators
    # 2 rounds = 4 animators
    # 3 rounds = 8 animators
    # 4 rounds = 16 animators

    animator_count = 2 ** rounds

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
    # SEARCH MESSAGE
    # ========================================================

    await interaction.response.send_message(
        "🔎 **Selecting animators from the "
        "KFSL animator database...**"
    )

    # ========================================================
    # SELECT ANIMATORS
    # ========================================================

    try:

        selected = (
            await sakuga.choose_battle_animators(
                animator_count
            )
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
    # NOT ENOUGH ANIMATORS
    # ========================================================

    if len(selected) < animator_count:

        sakuga.reset()

        await interaction.channel.send(
            f"❌ I could only find "
            f"**{len(selected)}** verified animators "
            f"with usable Sakugabooru clips, "
            f"but this tournament needs "
            f"**{animator_count}** animators."
        )

        return

    # ========================================================
    # USE EXACT NUMBER
    # ========================================================

    selected = selected[:animator_count]

    # ========================================================
    # CREATE ANIMATORS
    # ========================================================

    animators = []

    for candidate in selected:

        animator = Animator(
            candidate["name"]
        )

        animator.popularity = float(
            candidate.get(
                "quality",
                0
            )
        )

        animators.append(
            animator
        )

    # ========================================================
    # CREATE TOURNAMENT
    # ========================================================

    tournament = AnimatorBattle(
        animators,
        rounds=rounds,
        mode=mode.value,
    )

    bot.active_battles[
        guild_id
    ] = tournament

    # ========================================================
    # START MESSAGE
    # ========================================================

    await interaction.channel.send(
        "⚔️ **ANIMATOR TOURNAMENT STARTING!**\n\n"
        f"🏆 **{rounds} tournament rounds**\n"
        f"👥 **{animator_count} animators**\n"
        f"🎬 **{mode.name}**\n"
        f"⏱️ **{VOTE_TIME} seconds per match**\n\n"
        "❗ **Single elimination:**\n"
        "Lose once → eliminated.\n"
        "Win → advance to the next round.\n\n"
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
            "the animator tournament.\n"
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
        "       ANIMATOR BATTLE BOT"
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