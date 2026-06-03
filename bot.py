import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import aiohttp
import os
import urllib.parse
import hashlib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COC_API_KEY = os.getenv("COC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = os.getenv("GUILD_ID")

# Automatically fix the connection string if SQLAlchemy formatting is used
if DATABASE_URL and DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

LEADERBOARD_CHANNEL_ID = os.getenv("LEADERBOARD_CHANNEL_ID") 
LEADERBOARD_MESSAGE_ID = os.getenv("LEADERBOARD_MESSAGE_ID")

# --- UI Constants & Helpers ---
TROPHY_EMOJI = "🏆"
TH_EMOJIS = {
    16: "🏛️", 15: "🔺", 14: "🟩", 13: "🧊", 12: "⚡", 11: "🤍"
} 

def calc_legend_trophies(stars: int, dest: int) -> int:
    """Approximates standard Clash of Clans Legend League trophy gains."""
    if stars == 0:
        if dest < 10: return 0
        elif dest < 20: return 1
        elif dest < 30: return 2
        elif dest < 40: return 3
        else: return 4
    elif stars == 1:
        return 5 + ((dest - 50) // 5)
    elif stars == 2:
        return 16 + int((dest - 50) / 3.125)
    else:
        return 40

# --- Bot Initialization ---

class CoCStatsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db_pool = None
        self.session = None

    async def setup_hook(self):
        self.db_pool = await asyncpg.create_pool(dsn=DATABASE_URL)
        self.session = aiohttp.ClientSession(headers={
            "Authorization": f"Bearer {COC_API_KEY}",
            "Accept": "application/json"
        })
        
        self.auto_refresh_leaderboard.start()
        self.update_season_cache.start()
        self.poll_battlelogs.start()

    async def close(self):
        if self.session:
            await self.session.close()
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

    @tasks.loop(hours=24)
    async def update_season_cache(self):
        """Polls player profiles once every 24 hours to keep their League Season ID fresh."""
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            records = await conn.fetch("SELECT player_tag FROM tracked_players")
            tags = [r['player_tag'] for r in records]

            for tag in tags:
                encoded_tag = urllib.parse.quote(tag)
                url = f"https://api.clashofclans.com/v1/players/{encoded_tag}"
                
                try:
                    async with self.session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        
                        data = await resp.json()
                        season_id = data.get("currentLeagueSeasonId", 0)
                        if season_id is None:
                            season_id = 0
                            
                        updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

                        await conn.execute("""
                            INSERT INTO player_season_cache (player_tag, league_season_id, updated_at)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (player_tag) DO UPDATE 
                            SET league_season_id = EXCLUDED.league_season_id,
                                updated_at = EXCLUDED.updated_at
                        """, tag, season_id, updated_at)

                except Exception as e:
                    print(f"Error updating season cache for {tag}: {e}")

    @update_season_cache.before_loop
    async def before_update_season_cache(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def poll_battlelogs(self):
        """Polls the battlelog endpoint every 5 minutes and assigns the correct season ID."""
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            records = await conn.fetch("SELECT player_tag FROM tracked_players")
            tags = [r['player_tag'] for r in records]

            for tag in tags:
                encoded_tag = urllib.parse.quote(tag)
                
                # 1. Fetch the cached season ID
                season_id = await conn.fetchval("SELECT league_season_id FROM player_season_cache WHERE player_tag = $1", tag)

                if season_id is None:
                    # Cache Miss! Fetch it right now so we don't insert NULL/0.
                    profile_url = f"https://api.clashofclans.com/v1/players/{encoded_tag}"
                    try:
                        async with self.session.get(profile_url) as profile_resp:
                            if profile_resp.status == 200:
                                player_data = await profile_resp.json()
                                season_id = player_data.get("currentLeagueSeasonId", 0)
                                if season_id is None:
                                    season_id = 0
                                
                                await conn.execute("""
                                    INSERT INTO player_season_cache (player_tag, league_season_id)
                                    VALUES ($1, $2)
                                    ON CONFLICT (player_tag) DO UPDATE 
                                    SET league_season_id = EXCLUDED.league_season_id,
                                        updated_at = CURRENT_TIMESTAMP
                                """, tag, season_id)
                            else:
                                season_id = 0
                    except Exception as e:
                        print(f"Error fetching profile cache for {tag}: {e}")
                        season_id = 0

                # 2. Fetch the Battle Log
                battlelog_url = f"https://api.clashofclans.com/v1/players/{encoded_tag}/battlelog"
                
                try:
                    async with self.session.get(battlelog_url) as battle_resp:
                        if battle_resp.status != 200:
                            continue
                        battle_data = await battle_resp.json()
                        battles = battle_data.get("items", [])
                        
                        for battle in battles:
                            if battle.get("battleType") != "ranked":
                                continue
                                
                            stars = battle.get("stars", 0)
                            destruction = battle.get("destructionPercentage", 0)
                            is_attack = battle.get("attack", False)
                            opponent_tag = battle.get("opponentPlayerTag", "UNKNOWN")
                            army_share_code = battle.get("armyShareCode")
                            
                            hash_string = f"{tag}_{opponent_tag}_{stars}_{destruction}_{is_attack}"
                            battle_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

                            recorded_at = datetime.now(timezone.utc).replace(tzinfo=None)

                            # 3. Insert and Backfill NULLs from the ALTER TABLE statement
                            await conn.execute("""
                                INSERT INTO ranked_battles (
                                    player_tag, recorded_at, is_attack, opponent_player_tag, 
                                    stars, destruction_percentage, army_share_code, battle_hash, league_season_id
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                ON CONFLICT (battle_hash) DO UPDATE 
                                SET league_season_id = EXCLUDED.league_season_id 
                                WHERE ranked_battles.league_season_id IS NULL
                            """, tag, recorded_at, is_attack, opponent_tag, stars, destruction, army_share_code, battle_hash, season_id)

                except Exception as e:
                    print(f"Error polling battlelog for {tag}: {e}")

    @poll_battlelogs.before_loop
    async def before_poll_battlelogs(self):
        await self.wait_until_ready()

    @tasks.loop(hours=1)
    async def auto_refresh_leaderboard(self):
        if not LEADERBOARD_CHANNEL_ID or not LEADERBOARD_MESSAGE_ID:
            return

        channel = self.get_channel(int(LEADERBOARD_CHANNEL_ID))
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(LEADERBOARD_MESSAGE_ID))
            embed = await build_superwhoo_embed(self.db_pool)
            await message.edit(embed=embed)
        except discord.NotFound:
            print("Leaderboard message not found. Check your LEADERBOARD_MESSAGE_ID.")
        except Exception as e:
            print(f"Error auto-refreshing leaderboard: {e}")

    @auto_refresh_leaderboard.before_loop
    async def before_auto_refresh(self):
        await self.wait_until_ready()


bot = CoCStatsBot()


def format_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag

async def build_superwhoo_embed(db_pool) -> discord.Embed:
    query = """
    SELECT player_tag, COUNT(*) as superwhoo_count
    FROM (
        SELECT player_tag FROM ranked_battles WHERE destruction_percentage BETWEEN 95 AND 99
        UNION ALL
        SELECT attacker_tag AS player_tag FROM war_attacks WHERE destruction_percentage BETWEEN 95 AND 99
    ) combined
    GROUP BY player_tag
    ORDER BY superwhoo_count DESC
    LIMIT 10;
    """
    
    async with db_pool.acquire() as conn:
        records = await conn.fetch(query)

    embed = discord.Embed(
        title="🏆 Global Superwhoo Leaderboard", 
        color=discord.Color.dark_purple(),
        description="Ranked and War Attacks ending in 95-99% Destruction"
    )

    if not records:
        embed.add_field(name="No data yet", value="No superwhoos have been recorded.", inline=False)
        return embed

    for i, record in enumerate(records, start=1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔸"
        embed.add_field(
            name=f"{medal} #{i} | {record['player_tag']}", 
            value=f"**{record['superwhoo_count']}** Superwhoos", 
            inline=False
        )
        
    embed.set_footer(text="Data is tracked globally.")
    return embed


# --- Text Commands ---

@bot.command(name="cocsync")
@commands.has_permissions(administrator=True)
async def cocsync(ctx: commands.Context, scope: str = "guild"):
    if scope.lower() == "global":
        await ctx.send("Syncing slash commands globally... This may take up to an hour to appear.")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Successfully synced **{len(synced)}** commands globally.")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands globally: {e}")
    else:
        if not GUILD_ID:
            return await ctx.send("❌ `GUILD_ID` is not set in your `.env` file. Please set it or run `!cocsync global`.")
            
        await ctx.send("Instantly syncing slash commands to this server...")
        try:
            target_guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=target_guild)
            synced = await bot.tree.sync(guild=target_guild)
            await ctx.send(f"✅ Successfully synced **{len(synced)}** commands instantly to this server.")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands to the server: {e}")


# --- Slash Commands ---

@bot.tree.command(name="track", description="Adds a specific player to the global tracker.")
@app_commands.describe(player_tag="The in-game tag of the player")
async def track(interaction: discord.Interaction, player_tag: str):
    tag = format_tag(player_tag)
    async with bot.db_pool.acquire() as conn:
        await conn.execute("INSERT INTO tracked_players (player_tag) VALUES ($1) ON CONFLICT (player_tag) DO NOTHING", tag)
    await interaction.response.send_message(f"✅ **{tag}** has been added to the global tracker.")


@bot.tree.command(name="track_clan", description="Adds all current members of a clan to the global tracker.")
@app_commands.describe(clan_tag="The in-game tag of the clan")
async def track_clan(interaction: discord.Interaction, clan_tag: str):
    tag = format_tag(clan_tag)
    encoded_tag = urllib.parse.quote(tag)
    url = f"https://api.clashofclans.com/v1/clans/{encoded_tag}/members"

    await interaction.response.defer()

    async with bot.session.get(url) as resp:
        if resp.status == 404: return await interaction.followup.send(f"❌ Clan **{tag}** not found.")
        elif resp.status != 200: return await interaction.followup.send(f"❌ Clash of Clans API returned an error: HTTP {resp.status}")
        data = await resp.json()
        members = data.get("items", [])

    if not members: return await interaction.followup.send(f"⚠️ No members found in clan **{tag}**.")
    player_tags = [(m["tag"],) for m in members]

    async with bot.db_pool.acquire() as conn:
        await conn.executemany("INSERT INTO tracked_players (player_tag) VALUES ($1) ON CONFLICT (player_tag) DO NOTHING", player_tags)

    await interaction.followup.send(f"✅ Successfully added **{len(player_tags)}** members from clan **{tag}** to the tracker.")


@bot.tree.command(name="tracked", description="Displays all players currently tracked by the bot.")
async def tracked(interaction: discord.Interaction):
    await interaction.response.defer()
    async with bot.db_pool.acquire() as conn:
        records = await conn.fetch("SELECT player_tag FROM tracked_players ORDER BY player_tag")

    if not records: return await interaction.followup.send("⚠️ No players are currently being tracked.")

    tags = [record["player_tag"] for record in records]
    embeds, current_description, embed_count = [], "", 1
    
    for tag in tags:
        formatted_tag = f"`{tag}` "
        if len(current_description) + len(formatted_tag) > 4000:
            embeds.append(discord.Embed(title=f"📋 Tracked Players (Part {embed_count})", description=current_description, color=discord.Color.green()))
            current_description = formatted_tag
            embed_count += 1
        else:
            current_description += formatted_tag

    if current_description: embeds.append(discord.Embed(title=f"📋 Tracked Players (Part {embed_count})" if embed_count > 1 else "📋 Tracked Players", description=current_description, color=discord.Color.green()))

    if len(embeds) <= 10: await interaction.followup.send(content=f"Total Tracked: **{len(tags)}**", embeds=embeds)
    else: await interaction.followup.send(content=f"Total Tracked: **{len(tags)}** (Showing first 10 pages)", embeds=embeds[:10])


@bot.tree.command(name="battlelog", description="View the ranked battle log split into Offense and Defense.")
@app_commands.describe(
    player_tag="The in-game tag of the player",
    is_legend_1="Set to True if the player is in Legend 1 (uses daily 5AM resets instead of weekly)"
)
async def battlelog(interaction: discord.Interaction, player_tag: str, is_legend_1: bool = False):
    await interaction.response.defer()
    target_tag = format_tag(player_tag).replace("#", "")

    url = f"https://api.clashofclans.com/v1/players/%23{target_tag}"
    async with bot.session.get(url) as resp:
        if resp.status != 200:
            return await interaction.followup.send("❌ Could not find that player, or the API is currently unavailable.")
        d = await resp.json()

    league_tier = d.get('leagueTier', {})
    l_id = league_tier.get('id')
    l_name = league_tier.get('name', "Unranked")
    current_trophies = d.get('trophies', 0)

    # Defaults in case the league isn't in the DB yet
    limit = 15
    lg_emoji = "➖"

    if is_legend_1:
        limit = 8

    now_utc = datetime.now(timezone.utc)
    if is_legend_1 or "Legend League 1" in l_name:
        start_time = now_utc.replace(hour=5, minute=0, second=0, microsecond=0)
        if now_utc < start_time: start_time -= timedelta(days=1)
        end_time = start_time + timedelta(days=1)
    else:
        days_since_tuesday = (now_utc.weekday() - 1) % 7
        start_time = now_utc.replace(hour=5, minute=0, second=0, microsecond=0) - timedelta(days=days_since_tuesday)
        if now_utc < start_time: start_time -= timedelta(days=7)
        end_time = start_time + timedelta(days=7)

    start_str = start_time.strftime('%d %b').lstrip('0')
    end_str = end_time.strftime('%d %b').lstrip('0')
    duration_str = f"{start_str} – {end_str}"
    query_start = start_time.replace(tzinfo=None)

    async with bot.db_pool.acquire() as conn:
        # Fetch league metadata directly from the database
        if l_id:
            league_record = await conn.fetchrow("SELECT emoji, attack_limit FROM leagues WHERE league_id = $1", l_id)
            if league_record:
                if league_record['emoji']: 
                    lg_emoji = league_record['emoji']
                if league_record['attack_limit'] and not is_legend_1:
                    limit = league_record['attack_limit']

        # Fetch the internal DB battle records
        records = await conn.fetch("""
            SELECT recorded_at, is_attack, opponent_player_tag, stars, destruction_percentage
            FROM ranked_battles
            WHERE player_tag = $1 AND recorded_at >= $2
            ORDER BY recorded_at DESC
        """, f"#{target_tag}", query_start)

    if not records:
        return await interaction.followup.send(
            f"📉 No ranked battles found in the internal bot logs for **{d.get('name', 'Unknown')}** during this period ({duration_str})."
        )

    valid_logs = [dict(r) for r in records]
    opponent_tags = list(set(r['opponent_player_tag'] for r in valid_logs if r['opponent_player_tag'] != 'UNKNOWN'))
    name_cache = {}
    
    for o_tag in opponent_tags:
        if "UNKNOWN" in o_tag: continue
        o_url = f"https://api.clashofclans.com/v1/players/%23{o_tag.replace('#', '')}"
        try:
            async with bot.session.get(o_url) as o_resp:
                if o_resp.status == 200:
                    o_data = await o_resp.json()
                    name_cache[o_tag] = o_data.get('name', 'Unknown')
                else:
                    name_cache[o_tag] = o_tag
        except Exception:
            name_cache[o_tag] = "Unknown"

    for log in valid_logs:
        log['opp_name'] = name_cache.get(log['opponent_player_tag'], 'Unknown')

    offense_to_show = [b for b in valid_logs if b['is_attack']][:limit]
    defense_to_show = [b for b in valid_logs if not b['is_attack']][:limit]

    def get_averages_and_totals(logs, is_off):
        if not logs: return 0.0, 0.0, 0
        total_stars = sum(b['stars'] for b in logs)
        total_dest = sum(b['destruction_percentage'] for b in logs)
        total_trop = 0
        for b in logs:
            x = calc_legend_trophies(b['stars'], b['destruction_percentage'])
            if is_off: total_trop += x
            elif l_name == "Legend League 1" or is_legend_1: total_trop -= x
            else: total_trop += (40 - x)
        return total_stars / len(logs), total_dest / len(logs), total_trop

    off_avg_stars, off_avg_dest, total_off_trop = get_averages_and_totals(offense_to_show, is_off=True)
    def_avg_stars, def_avg_dest, total_def_trop = get_averages_and_totals(defense_to_show, is_off=False)

    th_level = d.get('townHallLevel', 1)
    th_emoji = TH_EMOJIS.get(th_level, "🏘️")

    embed = discord.Embed(
        title=f"{d.get('name', 'Unknown')} (#{target_tag})",
        url=f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={target_tag}",
        color=discord.Color.brand_red()
    )
    embed.description = (
        f"{th_emoji} **{th_level}** {TROPHY_EMOJI} **{current_trophies}** {lg_emoji} **{l_name}**\n\n"
        f"**Overview ({duration_str})**\n"
        f"⚔️ **Off:** {off_avg_stars:.2f} ★ | {off_avg_dest:.1f}%\n"
        f"🛡️ **Def:** {def_avg_stars:.2f} ★ | {def_avg_dest:.1f}%\n\u200b"
    )

    def build_column_text(logs, is_offense):
        if not logs:
            return "```ansi\n\u001b[0;36mNo logs yet.\u001b[0m\n```"

        text = ""
        for b in logs:
            stars = b['stars']
            dest = b['destruction_percentage']
            x = calc_legend_trophies(stars, dest)
            trop_change = x if is_offense else (-x if l_name == "Legend League 1" or is_legend_1 else 40 - x)
            trop_str = f"+{trop_change}" if trop_change > 0 else str(trop_change) if trop_change < 0 else "0"

            safe_name = "".join(c for c in b.get('opp_name', 'Unknown') if c.isascii()).replace('`', "'").strip()
            name_col = (safe_name[:6] + "..").ljust(8) if len(safe_name) > 8 else safe_name.ljust(8)
            dest_col = f"{dest}%".rjust(4)
            star_str = "★" * stars + "☆" * (3 - stars)
            trop_col = trop_str.rjust(3)

            if is_offense and dest == 100: ansi_start, ansi_end = "\u001b[1;33m", "\u001b[0m"
            elif not is_offense and dest == 100: ansi_start, ansi_end = "\u001b[1;31m", "\u001b[0m"
            else: ansi_start, ansi_end = "", ""

            entry = f"{ansi_start}{name_col} {dest_col} {star_str} {trop_col}  {ansi_end}\n"
            if len(text) + len(entry) > 950:
                text += "...\n"; break
            text += entry
        return f"```ansi\n{text}```"

    embed.add_field(
        name=f"⚔️ Offense ({len(offense_to_show)}/{limit}) | +{total_off_trop} {TROPHY_EMOJI}", 
        value=build_column_text(offense_to_show, is_offense=True), 
        inline=True
    )
    embed.add_field(
        name=f"🛡️ Defense ({len(defense_to_show)}/{limit}) | {total_def_trop:+} {TROPHY_EMOJI}", 
        value=build_column_text(defense_to_show, is_offense=False), 
        inline=True
    )

    await interaction.followup.send(embed=embed)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)