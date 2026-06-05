import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import aiohttp
import asyncio
import os
import urllib.parse
import hashlib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COC_API_KEY = os.getenv("COC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = os.getenv("GUILD_ID")

if DATABASE_URL and DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

LEADERBOARD_CHANNEL_ID = os.getenv("LEADERBOARD_CHANNEL_ID")
LEADERBOARD_MESSAGE_ID = os.getenv("LEADERBOARD_MESSAGE_ID")

# ---------------------------------------------------------------------------
# UI Constants
# ---------------------------------------------------------------------------
TROPHY_EMOJI = "🏆"
TH_EMOJIS = {
    16: "🏛️", 15: "🔺", 14: "🟩", 13: "🧊", 12: "⚡", 11: "🤍"
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def calc_legend_trophies(stars: int, dest: int) -> int:
    if stars == 0:
        if dest < 10:   return 0
        elif dest < 20: return 1
        elif dest < 30: return 2
        elif dest < 40: return 3
        else:           return 4
    elif stars == 1:
        return 5 + ((dest - 50) // 5)
    elif stars == 2:
        return 16 + int((dest - 50) / 3.125)
    else:
        return 40


def format_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag


def parse_coc_time(time_str: str) -> datetime:
    if not time_str:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        return datetime.strptime(time_str, "%Y%m%dT%H%M%S.%fZ")
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Discord UI Views
# ---------------------------------------------------------------------------
class BattlelogView(discord.ui.View):
    def __init__(self, bot, player_tag, league_season_id, current_trophies, l_id, is_legend_1):
        super().__init__(timeout=300)
        self.bot = bot
        self.player_tag = player_tag
        self.league_season_id = league_season_id
        self.current_trophies = current_trophies
        self.l_id = l_id
        self.is_legend_1 = is_legend_1

    @discord.ui.button(label="Trophy Graph", emoji="📈", style=discord.ButtonStyle.primary)
    async def trophy_graph(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        async with self.bot.db_pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT recorded_at, is_attack, stars, destruction_percentage
                FROM ranked_battles
                WHERE player_tag = $1 AND league_season_id = $2
                ORDER BY recorded_at ASC
            """, self.player_tag, self.league_season_id)

        if not records:
            return await interaction.followup.send(
                "⚠️ Not enough data recorded this season to build a graph.",
                ephemeral=True
            )

        min_date = None
        for r in records:
            shifted_dt = r['recorded_at'] - timedelta(hours=5)
            if min_date is None or shifted_dt.date() < min_date:
                min_date = shifted_dt.date()
        if min_date is None:
            min_date = (datetime.now(timezone.utc) - timedelta(hours=5)).date()

        current_coc_date = (datetime.now(timezone.utc) - timedelta(hours=5)).date()

        total_net_gain = 0
        for r in records:
            x = calc_legend_trophies(r['stars'], r['destruction_percentage'])
            if r['is_attack']:
                total_net_gain += x
            else:
                if self.l_id == 105000036 or self.is_legend_1:
                    total_net_gain -= x
                else:
                    total_net_gain += (40 - x)

        start_trophies    = self.current_trophies - total_net_gain
        running_trophies  = start_trophies
        peak_trophies     = start_trophies
        day_points, labels = [], []
        battle_idx = 0

        days_tracked       = (current_coc_date - min_date).days + 1
        total_days_to_plot = max(7, days_tracked + 2)

        for i in range(total_days_to_plot):
            target_date = min_date + timedelta(days=i)
            labels.append(target_date.strftime("%b %d"))

            if target_date > current_coc_date:
                day_points.append(None)
                continue

            while battle_idx < len(records):
                r = records[battle_idx]
                b_date = (r['recorded_at'] - timedelta(hours=5)).date()
                if b_date == target_date:
                    delta = calc_legend_trophies(r['stars'], r['destruction_percentage'])
                    if r['is_attack']:
                        running_trophies += delta
                    else:
                        if self.l_id == 105000036 or self.is_legend_1:
                            running_trophies -= delta
                        else:
                            running_trophies += (40 - delta)
                    if running_trophies > peak_trophies:
                        peak_trophies = running_trophies
                    battle_idx += 1
                elif b_date > target_date:
                    break
                else:
                    battle_idx += 1

            day_points.append(running_trophies)

        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": "Trophies",
                    "data": day_points,
                    "borderColor": "#3498db",
                    "backgroundColor": "rgba(52, 152, 219, 0.1)",
                    "fill": True,
                    "borderWidth": 4,
                    "pointRadius": 5,
                    "spanGaps": False
                }]
            },
            "options": {
                "plugins": {
                    "legend": {"labels": {"font": {"size": 18}}},
                    "title": {
                        "display": True,
                        "text": f"Tracked Trophy Progression - {self.player_tag}",
                        "font": {"size": 26}
                    },
                    "annotation": {
                        "annotations": {
                            "line1": {
                                "type": "line",
                                "yMin": start_trophies,
                                "yMax": start_trophies,
                                "borderColor": "rgba(231, 76, 60, 0.8)",
                                "borderWidth": 3,
                                "borderDash": [5, 5],
                                "label": {
                                    "display": True,
                                    "content": f"Baseline ({start_trophies})",
                                    "position": "start",
                                    "backgroundColor": "rgba(231, 76, 60, 0.8)",
                                    "font": {"size": 16}
                                }
                            }
                        }
                    }
                },
                "scales": {
                    "x": {
                        "title": {"display": True, "text": "Date (Reset at 5AM UTC)", "font": {"size": 18}},
                        "ticks": {"font": {"size": 14}}
                    },
                    "y": {
                        "title": {"display": True, "text": "Cumulative Trophies", "font": {"size": 18}},
                        "ticks": {"font": {"size": 16}}
                    }
                }
            }
        }

        qc_payload = {
            "chart": chart_config,
            "width": 1000,
            "height": 650,
            "backgroundColor": "white",
            "devicePixelRatio": 2.0
        }

        chart_short_url = ""
        try:
            async with self.bot.session.post("https://quickchart.io/chart/create", json=qc_payload) as qc_resp:
                if qc_resp.status == 200:
                    qc_data = await qc_resp.json()
                    chart_short_url = qc_data.get("url", "")
        except Exception as e:
            print(f"[trophy_graph] QuickChart error: {e}")

        stats = (
            f"**Tracking Began:** {min_date.strftime('%b %d, %Y')}\n"
            f"**Baseline Trophies:** {start_trophies} {TROPHY_EMOJI}\n"
            f"**Current Trophies:** {self.current_trophies} {TROPHY_EMOJI}\n"
            f"**Peak Trophies:** {peak_trophies} {TROPHY_EMOJI}\n"
            f"**Tracked Net Gain:** {self.current_trophies - start_trophies:+} {TROPHY_EMOJI}"
        )
        embed = discord.Embed(
            title=f"📈 Trophy Timeline: {self.player_tag}",
            description=stats,
            color=discord.Color.blue()
        )
        if chart_short_url:
            embed.set_image(url=chart_short_url)
        else:
            embed.set_footer(text="⚠️ Graph image generation failed.")
        await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------
class CoCStatsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db_pool = None
        self.session = None

    async def setup_hook(self):
        self.db_pool = await asyncpg.create_pool(dsn=DATABASE_URL)
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {COC_API_KEY}",
                "Accept": "application/json"
            },
            timeout=timeout
        )
        self.auto_refresh_leaderboard.start()
        self.update_season_cache.start()
        self.poll_battlelogs.start()
        self.poll_league_groups.start()
        self.poll_cwl_wars.start()

    async def close(self):
        if self.session:
            await self.session.close()
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

    # -----------------------------------------------------------------------
    # Endpoint 1 — GET /v1/players/{tag}
    # Writes: player_season_cache (now including clan_tag)
    # Runs:   every hour
    # -----------------------------------------------------------------------
    @tasks.loop(hours=1)
    async def update_season_cache(self):
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT player_tag FROM tracked_players")
        tags = [r['player_tag'] for r in rows]

        for tag in tags:
            encoded_tag = urllib.parse.quote(tag)
            url = f"https://api.clashofclans.com/v1/players/{encoded_tag}"
            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        print(f"[update_season_cache] {tag}: HTTP {resp.status}")
                        continue
                    data = await resp.json()

                player_name  = data.get("name", "")
                season_id    = data.get("currentLeagueSeasonId") or 0
                group_tag    = data.get("currentLeagueGroupTag")
                clan_tag     = data.get("clan", {}).get("tag")
                updated_at   = datetime.now(timezone.utc).replace(tzinfo=None)

                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO player_season_cache
                            (player_tag, player_name, league_season_id, league_group_tag, clan_tag, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (player_tag) DO UPDATE SET
                            player_name      = EXCLUDED.player_name,
                            league_season_id = EXCLUDED.league_season_id,
                            league_group_tag = EXCLUDED.league_group_tag,
                            clan_tag         = EXCLUDED.clan_tag,
                            updated_at       = EXCLUDED.updated_at
                    """, tag, player_name, season_id, group_tag, clan_tag, updated_at)

            except Exception as e:
                print(f"[update_season_cache ERROR] {tag}: {e}")

            await asyncio.sleep(0.2)

    @update_season_cache.before_loop
    async def before_update_season_cache(self):
        await self.wait_until_ready()

    # -----------------------------------------------------------------------
    # Endpoint 2 — GET /v1/players/{tag}/battlelog
    # Writes: ranked_battles
    # Runs:   every 5 minutes
    # -----------------------------------------------------------------------
    @tasks.loop(minutes=5)
    async def poll_battlelogs(self):
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tp.player_tag,
                       COALESCE(psc.league_season_id, 0) AS league_season_id
                FROM tracked_players tp
                LEFT JOIN player_season_cache psc
                       ON tp.player_tag = psc.player_tag
            """)

        for row in rows:
            tag       = row['player_tag']
            season_id = row['league_season_id'] or 0
            encoded   = urllib.parse.quote(tag)
            url       = f"https://api.clashofclans.com/v1/players/{encoded}/battlelog"

            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data    = await resp.json()
                    battles = data.get("items", [])

                async with self.db_pool.acquire() as conn:
                    for battle in battles:
                        if battle.get("battleType") != "ranked":
                            continue

                        stars        = battle.get("stars", 0)
                        destruction  = battle.get("destructionPercentage", 0)
                        is_attack    = battle.get("attack", False)
                        opponent_tag = battle.get("opponentPlayerTag") or "UNKNOWN"
                        army_code    = battle.get("armyShareCode")

                        hash_input   = f"{tag}_{opponent_tag}_{stars}_{destruction}_{is_attack}"
                        battle_hash  = hashlib.sha256(hash_input.encode()).hexdigest()
                        recorded_at  = datetime.now(timezone.utc).replace(tzinfo=None)

                        await conn.execute("""
                            INSERT INTO ranked_battles (
                                player_tag, recorded_at, is_attack, opponent_player_tag,
                                stars, destruction_percentage, army_share_code,
                                battle_hash, league_season_id
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (battle_hash) DO UPDATE SET
                                league_season_id = EXCLUDED.league_season_id
                            WHERE ranked_battles.league_season_id IS NULL
                        """, tag, recorded_at, is_attack, opponent_tag,
                            stars, destruction, army_code, battle_hash, season_id)

            except Exception as e:
                print(f"[poll_battlelogs ERROR] {tag}: {e}")

            await asyncio.sleep(0.2)

    @poll_battlelogs.before_loop
    async def before_poll_battlelogs(self):
        await self.wait_until_ready()

    # -----------------------------------------------------------------------
    # Endpoint 3 — league group data (CWL dependencies removed)
    # Writes: league_group_rankings + league_history
    # Runs:   every 30 minutes
    # -----------------------------------------------------------------------
    @tasks.loop(minutes=30)
    async def poll_league_groups(self):
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            group_rows = await conn.fetch("""
                SELECT DISTINCT ON (league_group_tag, league_season_id)
                    player_tag, league_group_tag, league_season_id
                FROM player_season_cache
                WHERE league_group_tag IS NOT NULL
                  AND league_season_id IS NOT NULL
                  AND league_season_id > 0
                ORDER BY league_group_tag, league_season_id, player_tag
            """)

            tracked_set = set(
                r['player_tag']
                for r in await conn.fetch("SELECT player_tag FROM tracked_players")
            )

        for grp in group_rows:
            player_tag = grp['player_tag']
            group_tag  = grp['league_group_tag']
            season_id  = grp['league_season_id']

            group_data = await self._fetch_league_group(player_tag, group_tag, season_id)
            if group_data is None:
                continue

            await self._process_league_group(group_data, group_tag, season_id, tracked_set)
            await asyncio.sleep(0.5)

    @poll_league_groups.before_loop
    async def before_poll_league_groups(self):
        await self.wait_until_ready()

    # -----------------------------------------------------------------------
    # CWL War Discovery Pipeline
    # Endpoint: /v1/clans/{clan_tag}/currentwar/leaguegroup
    # Writes: wars, war_attacks
    # Runs:   every 5 minutes
    # -----------------------------------------------------------------------
    @tasks.loop(minutes=5)
    async def poll_cwl_wars(self):
        if not self.db_pool or not self.session:
            return

        async with self.db_pool.acquire() as conn:
            clan_rows = await conn.fetch("""
                SELECT DISTINCT clan_tag 
                FROM player_season_cache 
                WHERE clan_tag IS NOT NULL
            """)
            tracked_set = set(
                r['player_tag'] for r in await conn.fetch("SELECT player_tag FROM tracked_players")
            )

        seen_war_tags = set()
        
        # Discover all active war tags across cached clans
        for row in clan_rows:
            clan_tag = row['clan_tag']
            encoded_clan = urllib.parse.quote(clan_tag)
            url = f"https://api.clashofclans.com/v1/clans/{encoded_clan}/currentwar/leaguegroup"
            
            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    group_data = await resp.json()
            except Exception as e:
                print(f"[poll_cwl_wars ERROR] group fetch for {clan_tag}: {e}")
                continue

            for round_data in group_data.get("rounds", []):
                for war_tag in round_data.get("warTags", []):
                    if war_tag != "#0":
                        seen_war_tags.add(war_tag)

            await asyncio.sleep(0.2)

        # Process deduplicated wars
        for war_tag in seen_war_tags:
            await self._process_cwl_war(war_tag, tracked_set)
            await asyncio.sleep(0.2)

    @poll_cwl_wars.before_loop
    async def before_poll_cwl_wars(self):
        await self.wait_until_ready()

    # -----------------------------------------------------------------------
    # Endpoint 3 helper — fetch league group JSON
    # -----------------------------------------------------------------------
    async def _fetch_league_group(
        self, player_tag: str, group_tag: str, season_id: int
    ) -> dict | None:
        encoded_group  = urllib.parse.quote(group_tag)
        encoded_player = urllib.parse.quote(player_tag)
        url = (
            f"https://api.clashofclans.com/v1/leaguegroup/"
            f"{encoded_group}/{season_id}"
            f"?playerTag={encoded_player}"
        )
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    print(f"[_fetch_league_group] group={group_tag}: HTTP {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            print(f"[_fetch_league_group ERROR] group={group_tag}: {e}")
            return None

    # -----------------------------------------------------------------------
    # Endpoint 3 processor — league_group_rankings + league_history
    # -----------------------------------------------------------------------
    async def _process_league_group(
        self,
        group_data: dict,
        group_tag: str,
        season_id: int,
        tracked_set: set,
    ):
        members = group_data.get("members", [])

        async with self.db_pool.acquire() as conn:
            for rank, member in enumerate(members, start=1):
                m_tag = member.get("playerTag") or member.get("tag")
                if not m_tag or m_tag not in tracked_set:
                    continue

                # --- league_group_rankings ---
                try:
                    await conn.execute("""
                        INSERT INTO league_group_rankings
                            (player_tag, league_group_tag, league_season_id, tournament_rank)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (player_tag, league_group_tag, league_season_id)
                        DO UPDATE SET tournament_rank = EXCLUDED.tournament_rank
                    """, m_tag, group_tag, season_id, rank)
                except Exception as e:
                    print(f"[_process_league_group] rankings insert error {m_tag}: {e}")

                # --- league_history ---
                attack_logs  = member.get("attackLogs", [])
                defense_logs = member.get("defenseLogs", [])

                attack_stars  = sum(a.get("stars", 0) for a in attack_logs)
                defense_stars = sum(d.get("stars", 0) for d in defense_logs)
                attack_wins   = len(attack_logs)
                defense_losses = len(defense_logs)

                league_trophies = member.get("trophies", 0)

                league_id_val   = None
                max_battles_val = 0

                member_league = member.get("league", {})
                if member_league:
                    league_id_val = member_league.get("id")

                if league_id_val:
                    lg_row = await conn.fetchrow(
                        "SELECT attack_limit FROM leagues WHERE league_id = $1",
                        league_id_val
                    )
                    if lg_row and lg_row['attack_limit']:
                        max_battles_val = lg_row['attack_limit']

                attack_losses  = max(0, max_battles_val - attack_wins)
                defense_wins   = max(0, max_battles_val - defense_losses)

                try:
                    await conn.execute("""
                        INSERT INTO league_history (
                            player_tag, league_season_id, league_id, placement,
                            league_trophies, attack_wins, attack_losses, attack_stars,
                            defense_wins, defense_losses, defense_stars, max_battles
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (player_tag, league_season_id) DO UPDATE SET
                            league_id       = EXCLUDED.league_id,
                            placement       = EXCLUDED.placement,
                            league_trophies = EXCLUDED.league_trophies,
                            attack_wins     = EXCLUDED.attack_wins,
                            attack_losses   = EXCLUDED.attack_losses,
                            attack_stars    = EXCLUDED.attack_stars,
                            defense_wins    = EXCLUDED.defense_wins,
                            defense_losses  = EXCLUDED.defense_losses,
                            defense_stars   = EXCLUDED.defense_stars,
                            max_battles     = EXCLUDED.max_battles
                    """, m_tag, season_id, league_id_val, rank,
                        league_trophies, attack_wins, attack_losses, attack_stars,
                        defense_wins, defense_losses, defense_stars, max_battles_val)
                except Exception as e:
                    print(f"[_process_league_group] history insert error {m_tag}: {e}")

    # -----------------------------------------------------------------------
    # Endpoint 4 helper — fetch + persist one CWL war
    # Writes: wars, war_attacks
    # -----------------------------------------------------------------------
    async def _process_cwl_war(self, war_tag: str, tracked_set: set):
        encoded = urllib.parse.quote(war_tag)
        url = f"https://api.clashofclans.com/v1/clanwarleagues/wars/{encoded}"

        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return
                war_data = await resp.json()
        except Exception as e:
            print(f"[_process_cwl_war ERROR] war_tag={war_tag}: {e}")
            return

        state = war_data.get("state", "unknown")
        if state not in ("inWar", "warEnded"):
            return

        clan_data      = war_data.get("clan", {})
        opponent_data  = war_data.get("opponent", {})
        clan_tag       = clan_data.get("tag")
        opp_clan_tag   = opponent_data.get("tag")
        team_size      = war_data.get("teamSize", 0)
        atk_per_member = war_data.get("attacksPerMember", 1)
        prep_time      = parse_coc_time(war_data.get("preparationStartTime"))
        start_time     = parse_coc_time(war_data.get("startTime"))
        end_time       = parse_coc_time(war_data.get("endTime"))

        async with self.db_pool.acquire() as conn:
            war_id = await conn.fetchval("""
                SELECT war_id FROM wars
                WHERE clan_tag = $1
                  AND opponent_clan_tag = $2
                  AND preparation_start_time = $3
            """, clan_tag, opp_clan_tag, prep_time)

            if war_id is None:
                try:
                    war_id = await conn.fetchval("""
                        INSERT INTO wars (
                            clan_tag, opponent_clan_tag, team_size, attacks_per_member,
                            preparation_start_time, start_time, end_time,
                            war_state, war_type
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'cwl')
                        RETURNING war_id
                    """, clan_tag, opp_clan_tag, team_size, atk_per_member,
                        prep_time, start_time, end_time, state)
                except asyncpg.UniqueViolationError:
                    war_id = await conn.fetchval("""
                        SELECT war_id FROM wars
                        WHERE clan_tag = $1
                          AND opponent_clan_tag = $2
                          AND preparation_start_time = $3
                    """, clan_tag, opp_clan_tag, prep_time)
            else:
                await conn.execute("""
                    UPDATE wars
                    SET war_state = $1, end_time = $2
                    WHERE war_id = $3
                """, state, end_time, war_id)

            if not war_id:
                print(f"[_process_cwl_war] Could not resolve war_id for {war_tag}")
                return

            for side in (clan_data, opponent_data):
                for member in side.get("members", []):
                    for attack in member.get("attacks", []):
                        attacker_tag = attack.get("attackerTag")
                        defender_tag = attack.get("defenderTag")

                        if (
                            attacker_tag not in tracked_set
                            and defender_tag not in tracked_set
                        ):
                            continue

                        stars       = attack.get("stars", 0)
                        destruction = attack.get("destructionPercentage", 0)
                        duration    = attack.get("duration", 0)
                        order       = attack.get("order", 0)

                        existing = await conn.fetchval("""
                            SELECT attack_id FROM war_attacks
                            WHERE war_id = $1
                              AND attacker_tag = $2
                              AND attack_order = $3
                        """, war_id, attacker_tag, order)

                        if existing is None:
                            try:
                                await conn.execute("""
                                    INSERT INTO war_attacks (
                                        war_id, attacker_tag, defender_tag,
                                        stars, destruction_percentage,
                                        duration_seconds, attack_order
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                                """, war_id, attacker_tag, defender_tag,
                                    stars, destruction, duration, order)
                            except Exception as e:
                                print(f"[_process_cwl_war] attack insert error: {e}")

    # -----------------------------------------------------------------------
    # Leaderboard auto-refresh
    # -----------------------------------------------------------------------
    @tasks.loop(hours=1)
    async def auto_refresh_leaderboard(self):
        if not LEADERBOARD_CHANNEL_ID or not LEADERBOARD_MESSAGE_ID:
            return
        channel = self.get_channel(int(LEADERBOARD_CHANNEL_ID))
        if not channel:
            return
        try:
            message = await channel.fetch_message(int(LEADERBOARD_MESSAGE_ID))
            embed   = await build_superwhoo_embed(self.db_pool)
            await message.edit(embed=embed)
        except discord.NotFound:
            print("[auto_refresh_leaderboard] Message not found.")
        except Exception as e:
            print(f"[auto_refresh_leaderboard ERROR] {e}")

    @auto_refresh_leaderboard.before_loop
    async def before_auto_refresh(self):
        await self.wait_until_ready()


# ---------------------------------------------------------------------------
# Bot instance
# ---------------------------------------------------------------------------
bot = CoCStatsBot()


# ---------------------------------------------------------------------------
# Leaderboard embed builder
# ---------------------------------------------------------------------------
async def build_superwhoo_embed(db_pool) -> discord.Embed:
    query = """
        SELECT player_tag, COUNT(*) AS superwhoo_count
        FROM (
            SELECT player_tag FROM ranked_battles
            WHERE destruction_percentage BETWEEN 95 AND 99
            UNION ALL
            SELECT attacker_tag AS player_tag FROM war_attacks
            WHERE destruction_percentage BETWEEN 95 AND 99
        ) combined
        GROUP BY player_tag
        ORDER BY superwhoo_count DESC
        LIMIT 10
    """
    async with db_pool.acquire() as conn:
        records = await conn.fetch(query)

    embed = discord.Embed(
        title="🏆 Global Superwhoo Leaderboard",
        color=discord.Color.dark_purple(),
        description="Ranked and War Attacks ending in 95–99% Destruction"
    )
    if not records:
        embed.add_field(name="No data yet", value="No superwhoos recorded.", inline=False)
        return embed

    for i, r in enumerate(records, start=1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔸"
        embed.add_field(
            name=f"{medal} #{i} | {r['player_tag']}",
            value=f"**{r['superwhoo_count']}** Superwhoos",
            inline=False
        )
    embed.set_footer(text="Data is tracked globally.")
    return embed


# ---------------------------------------------------------------------------
# Text commands
# ---------------------------------------------------------------------------
@bot.command(name="cocsync")
@commands.has_permissions(administrator=True)
async def cocsync(ctx: commands.Context, scope: str = "guild"):
    if scope.lower() == "global":
        await ctx.send("Syncing slash commands globally…")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Synced **{len(synced)}** commands globally.")
        except Exception as e:
            await ctx.send(f"❌ Failed: {e}")
    else:
        if not GUILD_ID:
            return await ctx.send("❌ `GUILD_ID` not set in `.env`.")
        await ctx.send("Syncing slash commands to this server…")
        try:
            target = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=target)
            synced = await bot.tree.sync(guild=target)
            await ctx.send(f"✅ Synced **{len(synced)}** commands to this server.")
        except Exception as e:
            await ctx.send(f"❌ Failed: {e}")


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------
@bot.tree.command(name="refresh_leaderboard", description="Manually refresh the Superwhoo Leaderboard.")
async def refresh_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    await bot.auto_refresh_leaderboard()
    await interaction.followup.send("✅ Leaderboard refreshed.", ephemeral=True)


@bot.tree.command(name="track", description="Add a player to the global tracker.")
@app_commands.describe(player_tag="The in-game tag of the player")
async def track(interaction: discord.Interaction, player_tag: str):
    tag = format_tag(player_tag)
    async with bot.db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO tracked_players (player_tag) VALUES ($1) ON CONFLICT DO NOTHING", tag
        )
    await interaction.response.send_message(f"✅ **{tag}** added to the global tracker.")


@bot.tree.command(name="track_clan", description="Add all current members of a clan to the tracker.")
@app_commands.describe(clan_tag="The in-game tag of the clan")
async def track_clan(interaction: discord.Interaction, clan_tag: str):
    tag     = format_tag(clan_tag)
    encoded = urllib.parse.quote(tag)
    url     = f"https://api.clashofclans.com/v1/clans/{encoded}/members"
    await interaction.response.defer()

    try:
        async with bot.session.get(url) as resp:
            if resp.status == 404:
                return await interaction.followup.send(f"❌ Clan **{tag}** not found.")
            elif resp.status != 200:
                return await interaction.followup.send(f"❌ API error: HTTP {resp.status}")
            data    = await resp.json()
            members = data.get("items", [])
    except Exception as e:
        return await interaction.followup.send(f"❌ API request failed: {e}")

    if not members:
        return await interaction.followup.send(f"⚠️ No members found in clan **{tag}**.")

    player_tags = [(m["tag"],) for m in members]
    async with bot.db_pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO tracked_players (player_tag) VALUES ($1) ON CONFLICT DO NOTHING",
            player_tags
        )
    await interaction.followup.send(
        f"✅ Added **{len(player_tags)}** members from **{tag}** to the tracker."
    )


@bot.tree.command(name="tracked", description="Show all tracked players.")
async def tracked(interaction: discord.Interaction):
    await interaction.response.defer()
    async with bot.db_pool.acquire() as conn:
        records = await conn.fetch("SELECT player_tag FROM tracked_players ORDER BY player_tag")

    if not records:
        return await interaction.followup.send("⚠️ No players are currently tracked.")

    tags = [r["player_tag"] for r in records]
    embeds, current_desc, part = [], "", 1

    for tag in tags:
        chunk = f"`{tag}` "
        if len(current_desc) + len(chunk) > 4000:
            embeds.append(discord.Embed(
                title=f"📋 Tracked Players (Part {part})",
                description=current_desc,
                color=discord.Color.green()
            ))
            current_desc = chunk
            part += 1
        else:
            current_desc += chunk

    if current_desc:
        embeds.append(discord.Embed(
            title=f"📋 Tracked Players" + (f" (Part {part})" if part > 1 else ""),
            description=current_desc,
            color=discord.Color.green()
        ))

    send_embeds = embeds[:10]
    await interaction.followup.send(
        content=f"Total tracked: **{len(tags)}**",
        embeds=send_embeds
    )


@bot.tree.command(
    name="battlelog",
    description="View ranked battle log split into Offense and Defense."
)
@app_commands.describe(
    player_tag="The in-game tag of the player",
    is_legend_1="True if the player is in Legend 1 (daily 5AM resets)"
)
async def battlelog(interaction: discord.Interaction, player_tag: str, is_legend_1: bool = False):
    await interaction.response.defer()
    target_tag     = format_tag(player_tag)
    clean_tag      = target_tag.replace("#", "")

    url = f"https://api.clashofclans.com/v1/players/%23{clean_tag}"
    try:
        async with bot.session.get(url) as resp:
            if resp.status != 200:
                return await interaction.followup.send("❌ Player not found or API unavailable.")
            d = await resp.json()
    except Exception as e:
        return await interaction.followup.send(f"❌ API request failed: {e}")

    league_tier    = d.get("leagueTier", {}) or {}
    l_id           = league_tier.get("id")
    current_trophies = d.get("trophies", 0)

    limit    = 15
    lg_emoji = "➖"
    l_name   = "Unranked"

    if is_legend_1 or l_id == 105000036:
        limit = 8

    now_utc = datetime.now(timezone.utc)
    if is_legend_1 or l_id == 105000036:
        start_time = now_utc.replace(hour=5, minute=0, second=0, microsecond=0)
        if now_utc < start_time:
            start_time -= timedelta(days=1)
        end_time = start_time + timedelta(days=1)
    else:
        days_since_tuesday = (now_utc.weekday() - 1) % 7
        start_time = now_utc.replace(hour=5, minute=0, second=0, microsecond=0) - timedelta(days=days_since_tuesday)
        if now_utc < start_time:
            start_time -= timedelta(days=7)
        end_time = start_time + timedelta(days=6)

    start_str    = start_time.strftime('%d %b').lstrip('0')
    end_str      = end_time.strftime('%d %b').lstrip('0')
    duration_str = f"{start_str} – {end_str}"
    query_start  = start_time.replace(tzinfo=None)

    tournament_rank = None
    ssn_id          = None

    async with bot.db_pool.acquire() as conn:
        cache_row = await conn.fetchrow(
            "SELECT league_season_id, league_group_tag, clan_tag FROM player_season_cache WHERE player_tag = $1",
            target_tag
        )

        grp_tag = None
        clan_tag_cache = None
        if cache_row and cache_row['league_group_tag'] and cache_row['league_season_id']:
            grp_tag        = cache_row['league_group_tag']
            ssn_id         = cache_row['league_season_id']
            clan_tag_cache = cache_row['clan_tag']
        else:
            ssn_id         = d.get("currentLeagueSeasonId") or 0
            grp_tag        = d.get("currentLeagueGroupTag")
            clan_tag_cache = d.get("clan", {}).get("tag")
            if ssn_id or grp_tag or clan_tag_cache:
                try:
                    await conn.execute("""
                        INSERT INTO player_season_cache
                            (player_tag, player_name, league_season_id, league_group_tag, clan_tag)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (player_tag) DO UPDATE SET
                            player_name      = EXCLUDED.player_name,
                            league_season_id = EXCLUDED.league_season_id,
                            league_group_tag = EXCLUDED.league_group_tag,
                            clan_tag         = EXCLUDED.clan_tag,
                            updated_at       = CURRENT_TIMESTAMP
                    """, target_tag, d.get("name", ""), ssn_id, grp_tag, clan_tag_cache)
                except Exception as e:
                    print(f"[battlelog] cache self-heal failed for {target_tag}: {e}")

        if grp_tag and ssn_id:
            rank_row = await conn.fetchrow("""
                SELECT tournament_rank FROM league_group_rankings
                WHERE player_tag = $1
                  AND league_group_tag = $2
                  AND league_season_id = $3
            """, target_tag, grp_tag, ssn_id)
            if rank_row:
                tournament_rank = rank_row['tournament_rank']

        if l_id:
            lg_row = await conn.fetchrow(
                "SELECT league_name, emoji, attack_limit FROM leagues WHERE league_id = $1", l_id
            )
            if lg_row:
                l_name = lg_row['league_name'] or l_name
                if lg_row['emoji']:
                    lg_emoji = lg_row['emoji']
                if lg_row['attack_limit'] and not is_legend_1:
                    limit = lg_row['attack_limit']

        records = await conn.fetch("""
            SELECT recorded_at, is_attack, opponent_player_tag, stars, destruction_percentage
            FROM ranked_battles
            WHERE player_tag = $1 AND recorded_at >= $2
            ORDER BY recorded_at DESC
        """, target_tag, query_start)

    if not records:
        return await interaction.followup.send(
            f"📉 No ranked battles found for **{d.get('name', 'Unknown')}** during {duration_str}."
        )

    valid_logs       = [dict(r) for r in records]
    offense_to_show  = [b for b in valid_logs if     b['is_attack']][:limit]
    defense_to_show  = [b for b in valid_logs if not b['is_attack']][:limit]
    logs_to_display  = offense_to_show + defense_to_show

    opponent_tags = list(set(
        b['opponent_player_tag'] for b in logs_to_display
        if b.get('opponent_player_tag') and b['opponent_player_tag'] != 'UNKNOWN'
    ))

    async def fetch_opponent_name(o_tag):
        o_url = f"https://api.clashofclans.com/v1/players/%23{o_tag.replace('#', '')}"
        try:
            async with bot.session.get(o_url) as r:
                if r.status == 200:
                    return o_tag, (await r.json()).get('name', 'Unknown')
        except Exception:
            pass
        return o_tag, "Unknown"

    name_results = await asyncio.gather(*(fetch_opponent_name(t) for t in opponent_tags))
    name_cache   = dict(name_results)
    for log in logs_to_display:
        log['opp_name'] = name_cache.get(log['opponent_player_tag'], 'Unknown')

    def get_averages_and_totals(logs, is_off):
        if not logs:
            return 0.0, 0.0, 0
        total_stars = sum(b['stars']               for b in logs)
        total_dest  = sum(b['destruction_percentage'] for b in logs)
        total_trop  = 0
        for b in logs:
            x = calc_legend_trophies(b['stars'], b['destruction_percentage'])
            if is_off:
                total_trop += x
            elif l_id == 105000036 or is_legend_1:
                total_trop -= x
            else:
                total_trop += (40 - x)
        return total_stars / len(logs), total_dest / len(logs), total_trop

    off_avg_s, off_avg_d, total_off_trop = get_averages_and_totals(offense_to_show, True)
    def_avg_s, def_avg_d, total_def_trop = get_averages_and_totals(defense_to_show, False)

    th_level = d.get('townHallLevel', 1)
    th_emoji = TH_EMOJIS.get(th_level, "🏘️")

    embed = discord.Embed(
        title=f"{d.get('name', 'Unknown')} ({target_tag})",
        url=f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={clean_tag}",
        color=discord.Color.brand_red()
    )

    rank_str = f"🎖️ **Live Rank:** {tournament_rank}\n" if tournament_rank is not None else ""
    embed.description = (
        f"{th_emoji} **{th_level}** {TROPHY_EMOJI} **{current_trophies}** {lg_emoji} **{l_name}**\n\n"
        f"**Overview ({duration_str})**\n"
        f"{rank_str}"
        f"⚔️ **Off:** {off_avg_s:.2f} ★ | {off_avg_d:.1f}%\n"
        f"🛡️ **Def:** {def_avg_s:.2f} ★ | {def_avg_d:.1f}%\n\u200b"
    )

    def build_column_text(logs, is_offense):
        if not logs:
            return "```ansi\n\u001b[0;36mNo logs yet.\u001b[0m\n```"
        text = ""
        for b in logs:
            stars = b['stars']
            dest  = b['destruction_percentage']
            x     = calc_legend_trophies(stars, dest)
            trop_change = (
                x if is_offense
                else (-x if l_id == 105000036 or is_legend_1 else 40 - x)
            )
            trop_str = f"+{trop_change}" if trop_change > 0 else str(trop_change) if trop_change < 0 else "0"

            safe_name = "".join(c for c in b.get('opp_name', 'Unknown') if c.isascii()).replace('`', "'").strip()
            name_col  = (safe_name[:6] + "..").ljust(8) if len(safe_name) > 8 else safe_name.ljust(8)
            dest_col  = f"{dest}%".rjust(4)
            star_str  = "★" * stars + "☆" * (3 - stars)
            trop_col  = trop_str.rjust(3)

            if is_offense and dest == 100:
                ansi_s, ansi_e = "\u001b[1;33m", "\u001b[0m"
            elif not is_offense and dest == 100:
                ansi_s, ansi_e = "\u001b[1;31m", "\u001b[0m"
            else:
                ansi_s, ansi_e = "", ""

            entry = f"{ansi_s}{name_col} {dest_col} {star_str} {trop_col}  {ansi_e}\n"
            if len(text) + len(entry) > 950:
                text += "...\n"
                break
            text += entry
        return f"```ansi\n{text}```"

    embed.add_field(
        name=f"⚔️ Offense ({len(offense_to_show)}/{limit}) | +{total_off_trop} {TROPHY_EMOJI}",
        value=build_column_text(offense_to_show, True),
        inline=True
    )
    embed.add_field(
        name=f"🛡️ Defense ({len(defense_to_show)}/{limit}) | {total_def_trop:+} {TROPHY_EMOJI}",
        value=build_column_text(defense_to_show, False),
        inline=True
    )

    view = BattlelogView(bot, target_tag, ssn_id, current_trophies, l_id, is_legend_1)
    await interaction.followup.send(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Admin: Force-pull CWL data for a specific player right now
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="force_cwl_pull",
    description="[Admin] Immediately pull CWL data for a tracked player via their clan."
)
@app_commands.describe(player_tag="The in-game tag of the player")
@commands.has_permissions(administrator=True)
async def force_cwl_pull(interaction: discord.Interaction, player_tag: str):
    await interaction.response.defer()
    tag = format_tag(player_tag)
    results = []

    async with bot.db_pool.acquire() as conn:
        cache_row = await conn.fetchrow(
            "SELECT clan_tag FROM player_season_cache WHERE player_tag = $1", tag
        )
        tracked_set = set(
            r['player_tag'] for r in await conn.fetch("SELECT player_tag FROM tracked_players")
        )

    clan_tag = None
    if cache_row and cache_row['clan_tag']:
        clan_tag = cache_row['clan_tag']
    else:
        # Hydrate cache manually for this player
        encoded = urllib.parse.quote(tag)
        try:
            async with bot.session.get(f"https://api.clashofclans.com/v1/players/{encoded}") as resp:
                if resp.status == 200:
                    d         = await resp.json()
                    season_id = d.get("currentLeagueSeasonId") or 0
                    group_tag = d.get("currentLeagueGroupTag")
                    clan_tag  = d.get("clan", {}).get("tag")
                    
                    async with bot.db_pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO player_season_cache
                                (player_tag, player_name, league_season_id, league_group_tag, clan_tag)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (player_tag) DO UPDATE SET
                                player_name      = EXCLUDED.player_name,
                                league_season_id = EXCLUDED.league_season_id,
                                league_group_tag = EXCLUDED.league_group_tag,
                                clan_tag         = EXCLUDED.clan_tag,
                                updated_at       = CURRENT_TIMESTAMP
                        """, tag, d.get("name", ""), season_id, group_tag, clan_tag)
                    
                    results.append(f"✅ Fetched fresh profile, updated cached clan: {clan_tag}")
                else:
                    results.append("❌ Player profile fetch failed. Cannot discover clan.")
        except Exception as e:
            results.append(f"❌ Profile API request failed: {e}")

    if not clan_tag:
        results.append("⚠️ Player is not in a clan or clan could not be resolved. Aborting CWL pull.")
        return await interaction.followup.send("**Force CWL Pull Results:**\n" + "\n".join(results))

    encoded_clan = urllib.parse.quote(clan_tag)
    url = f"https://api.clashofclans.com/v1/clans/{encoded_clan}/currentwar/leaguegroup"
    
    seen_war_tags = set()
    try:
        async with bot.session.get(url) as resp:
            if resp.status == 200:
                group_data = await resp.json()
                for round_data in group_data.get("rounds", []):
                    for war_tag in round_data.get("warTags", []):
                        if war_tag != "#0":
                            seen_war_tags.add(war_tag)
                results.append(f"✅ Found {len(seen_war_tags)} valid war tags from clan {clan_tag} league group.")
            else:
                results.append(f"❌ Could not fetch CWL leaguegroup for clan {clan_tag} (HTTP {resp.status}).")
    except Exception as e:
        results.append(f"❌ API error on leaguegroup fetch: {e}")

    war_count = 0
    for war_tag in seen_war_tags:
        await bot._process_cwl_war(war_tag, tracked_set)
        war_count += 1
        await asyncio.sleep(0.2)

    if war_count > 0:
        results.append(f"✅ Processed {war_count} CWL war tag(s) and persisted attacks.")

    await interaction.followup.send(
        "**Force CWL Pull Results for {}:**\n{}".format(tag, "\n".join(results))
    )


# ---------------------------------------------------------------------------
# Admin: Force-refresh season cache for a player
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="force_cache_refresh",
    description="[Admin] Immediately refresh player_season_cache for a player."
)
@app_commands.describe(player_tag="The in-game tag of the player")
@commands.has_permissions(administrator=True)
async def force_cache_refresh(interaction: discord.Interaction, player_tag: str):
    await interaction.response.defer()
    tag     = format_tag(player_tag)
    encoded = urllib.parse.quote(tag)
    url     = f"https://api.clashofclans.com/v1/players/{encoded}"

    try:
        async with bot.session.get(url) as resp:
            if resp.status != 200:
                return await interaction.followup.send(f"❌ API returned HTTP {resp.status}")
            d = await resp.json()
    except Exception as e:
        return await interaction.followup.send(f"❌ Request failed: {e}")

    player_name = d.get("name", "")
    season_id   = d.get("currentLeagueSeasonId") or 0
    group_tag   = d.get("currentLeagueGroupTag")
    clan_tag    = d.get("clan", {}).get("tag")
    updated_at  = datetime.now(timezone.utc).replace(tzinfo=None)

    async with bot.db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO player_season_cache
                (player_tag, player_name, league_season_id, league_group_tag, clan_tag, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (player_tag) DO UPDATE SET
                player_name      = EXCLUDED.player_name,
                league_season_id = EXCLUDED.league_season_id,
                league_group_tag = EXCLUDED.league_group_tag,
                clan_tag         = EXCLUDED.clan_tag,
                updated_at       = EXCLUDED.updated_at
        """, tag, player_name, season_id, group_tag, clan_tag, updated_at)

    await interaction.followup.send(
        f"✅ Cache refreshed for **{player_name}** (`{tag}`)\n"
        f"season_id=`{season_id}` | group_tag=`{group_tag}` | clan_tag=`{clan_tag}`"
    )


# ---------------------------------------------------------------------------
# Admin: Debug — show last 10 war attacks
# ---------------------------------------------------------------------------
@bot.tree.command(name="debug_wars", description="[Admin] Show last 10 war attacks in the database.")
@commands.has_permissions(administrator=True)
async def debug_wars(interaction: discord.Interaction):
    await interaction.response.defer()
    async with bot.db_pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT a.attacker_tag, a.defender_tag, a.stars,
                   a.destruction_percentage, w.war_type,
                   w.clan_tag, w.opponent_clan_tag
            FROM war_attacks a
            JOIN wars w ON a.war_id = w.war_id
            ORDER BY a.recorded_at DESC
            LIMIT 10
        """)

    if not records:
        return await interaction.followup.send(
            "⚠️ No war attacks saved yet. Try `/force_cwl_pull` while a CWL is active."
        )

    embed = discord.Embed(title="🛠️ Debug: Last 10 War Attacks", color=discord.Color.green())
    for i, r in enumerate(records, start=1):
        label = "CWL" if r['war_type'] == "cwl" else "Regular"
        embed.add_field(
            name=f"{i}. {r['attacker_tag']} → {r['defender_tag']}",
            value=(
                f"**{r['stars']}⭐** | {r['destruction_percentage']}%\n"
                f"`{label}`: {r['clan_tag']} vs {r['opponent_clan_tag']}"
            ),
            inline=False
        )
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# Admin: Debug — show current state of player_season_cache
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="debug_cache",
    description="[Admin] Show player_season_cache entries."
)
@commands.has_permissions(administrator=True)
async def debug_cache(interaction: discord.Interaction):
    await interaction.response.defer()
    async with bot.db_pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT player_tag, player_name, league_season_id, league_group_tag, clan_tag, updated_at
            FROM player_season_cache
            ORDER BY updated_at DESC
            LIMIT 20
        """)

    if not records:
        return await interaction.followup.send("⚠️ player_season_cache is empty.")

    lines = []
    for r in records:
        lines.append(
            f"`{r['player_tag']}` | {r['player_name']} | "
            f"ssn={r['league_season_id']} | grp={r['league_group_tag']} | clan={r['clan_tag']} | "
            f"updated={r['updated_at'].strftime('%H:%M:%S') if r['updated_at'] else 'n/a'}"
        )

    embed = discord.Embed(
        title="🛠️ Debug: player_season_cache (last 20)",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# Admin: Debug — show ranked_battles count per player
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="debug_battles",
    description="[Admin] Show ranked battle counts per player."
)
@commands.has_permissions(administrator=True)
async def debug_battles(interaction: discord.Interaction):
    await interaction.response.defer()
    async with bot.db_pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT player_tag,
                   COUNT(*) FILTER (WHERE is_attack)      AS attacks,
                   COUNT(*) FILTER (WHERE NOT is_attack)  AS defenses
            FROM ranked_battles
            GROUP BY player_tag
            ORDER BY (attacks + defenses) DESC
            LIMIT 20
        """)

    if not records:
        return await interaction.followup.send("⚠️ ranked_battles is empty.")

    lines = [f"`{r['player_tag']}` — ⚔️{r['attacks']} atk / 🛡️{r['defenses']} def" for r in records]
    embed = discord.Embed(
        title="🛠️ Debug: ranked_battles counts",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# Admin: Full pipeline diagnostic for one player — shows every step
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="debug_pipeline",
    description="[Admin] Run the full data pipeline for one player and show every step."
)
@app_commands.describe(player_tag="The in-game tag of the player")
@commands.has_permissions(administrator=True)
async def debug_pipeline(interaction: discord.Interaction, player_tag: str):
    await interaction.response.defer()
    tag     = format_tag(player_tag)
    encoded = urllib.parse.quote(tag)
    lines   = []

    def log(msg: str):
        print(f"[debug_pipeline] {msg}")
        lines.append(msg)

    # ---- Step 1: Is the player tracked? ------------------------------------
    async with bot.db_pool.acquire() as conn:
        is_tracked = await conn.fetchval(
            "SELECT 1 FROM tracked_players WHERE player_tag = $1", tag
        )
    if not is_tracked:
        log(f"❌ STEP 1 FAIL — `{tag}` is not in tracked_players. Run `/track {tag}` first.")
        return await interaction.followup.send("\n".join(lines))
    log(f"✅ STEP 1 — `{tag}` found in tracked_players.")

    # ---- Step 2: Endpoint 1 — player profile --------------------------------
    profile_url = f"https://api.clashofclans.com/v1/players/{encoded}"
    try:
        async with bot.session.get(profile_url) as resp:
            status = resp.status
            if status != 200:
                log(f"❌ STEP 2 FAIL — Endpoint 1 returned HTTP {status}. "
                    f"Check COC_API_KEY and that the tag is valid.")
                return await interaction.followup.send("\n".join(lines))
            profile = await resp.json()
    except Exception as e:
        log(f"❌ STEP 2 FAIL — Endpoint 1 exception: {e}")
        return await interaction.followup.send("\n".join(lines))

    player_name  = profile.get("name", "?")
    season_id    = profile.get("currentLeagueSeasonId") or 0
    group_tag    = profile.get("currentLeagueGroupTag")
    clan_tag     = profile.get("clan", {}).get("tag")
    league_tier  = profile.get("leagueTier") or {}
    league_id    = league_tier.get("id")
    trophies     = profile.get("trophies", 0)
    log(
        f"✅ STEP 2 — Profile OK: name={player_name}, trophies={trophies}, "
        f"leagueTier.id={league_id}, season_id={season_id}, group_tag={group_tag}, clan_tag={clan_tag}"
    )

    if not league_id:
        log("⚠️  Player has no leagueTier — they are not in a ranked league this season. "
            "Ranked battles will not exist until they reach Legend League.")

    # ---- Step 3: Write player_season_cache ----------------------------------
    updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with bot.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO player_season_cache
                    (player_tag, player_name, league_season_id, league_group_tag, clan_tag, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (player_tag) DO UPDATE SET
                    player_name      = EXCLUDED.player_name,
                    league_season_id = EXCLUDED.league_season_id,
                    league_group_tag = EXCLUDED.league_group_tag,
                    clan_tag         = EXCLUDED.clan_tag,
                    updated_at       = EXCLUDED.updated_at
            """, tag, player_name, season_id, group_tag, clan_tag, updated_at)
        log("✅ STEP 3 — player_season_cache written.")
    except Exception as e:
        log(f"❌ STEP 3 FAIL — player_season_cache write error: {e}")
        return await interaction.followup.send("\n".join(lines))

    # ---- Step 4: Endpoint 2 — battlelog ------------------------------------
    battlelog_url = f"https://api.clashofclans.com/v1/players/{encoded}/battlelog"
    try:
        async with bot.session.get(battlelog_url) as resp:
            status = resp.status
            if status != 200:
                log(f"❌ STEP 4 FAIL — Endpoint 2 returned HTTP {status}.")
                return await interaction.followup.send("\n".join(lines))
            bl_data  = await resp.json()
            battles  = bl_data.get("items", [])
    except Exception as e:
        log(f"❌ STEP 4 FAIL — Endpoint 2 exception: {e}")
        return await interaction.followup.send("\n".join(lines))

    log(f"✅ STEP 4 — Battlelog fetched: {len(battles)} total battles returned by API.")

    if not battles:
        log("⚠️  Battlelog is empty — player has no recent battles at all.")
        return await interaction.followup.send("\n".join(lines))

    # Show the battleTypes present so we can see if any are "ranked"
    type_counts: dict[str, int] = {}
    for b in battles:
        bt = b.get("battleType", "unknown")
        type_counts[bt] = type_counts.get(bt, 0) + 1
    log(f"   battleType breakdown: { {k: v for k, v in type_counts.items()} }")

    ranked = [b for b in battles if b.get("battleType") == "ranked"]
    if not ranked:
        log("⚠️  None of the battles have battleType='ranked'. "
            "This means the player has not yet participated in Legend League ranked battles this season. "
            "Non-ranked battle types (regular, friendly, etc.) are intentionally ignored per spec.")
        return await interaction.followup.send("\n".join(lines))

    log(f"   {len(ranked)} ranked battle(s) found — attempting to insert into ranked_battles…")

    # ---- Step 5: Insert ranked battles -------------------------------------
    inserted = 0
    skipped  = 0
    errors   = 0
    try:
        async with bot.db_pool.acquire() as conn:
            for battle in ranked:
                stars        = battle.get("stars", 0)
                destruction  = battle.get("destructionPercentage", 0)
                is_attack    = battle.get("attack", False)
                opponent_tag = battle.get("opponentPlayerTag") or "UNKNOWN"
                army_code    = battle.get("armyShareCode")
                hash_input   = f"{tag}_{opponent_tag}_{stars}_{destruction}_{is_attack}"
                battle_hash  = hashlib.sha256(hash_input.encode()).hexdigest()
                recorded_at  = datetime.now(timezone.utc).replace(tzinfo=None)
                try:
                    result = await conn.execute("""
                        INSERT INTO ranked_battles (
                            player_tag, recorded_at, is_attack, opponent_player_tag,
                            stars, destruction_percentage, army_share_code,
                            battle_hash, league_season_id
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (battle_hash) DO UPDATE SET
                            league_season_id = EXCLUDED.league_season_id
                        WHERE ranked_battles.league_season_id IS NULL
                    """, tag, recorded_at, is_attack, opponent_tag,
                        stars, destruction, army_code, battle_hash, season_id)
                    if "INSERT 0 1" in result:
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    log(f"   ⚠️  Insert error on one battle: {e}")
    except Exception as e:
        log(f"❌ STEP 5 FAIL — DB connection error: {e}")
        return await interaction.followup.send("\n".join(lines))

    log(
        f"✅ STEP 5 — ranked_battles: {inserted} new row(s) inserted, "
        f"{skipped} already existed (skipped), {errors} error(s)."
    )

    # ---- Step 6: Verify DB row count ---------------------------------------
    async with bot.db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM ranked_battles WHERE player_tag = $1", tag
        )
    log(f"✅ STEP 6 — ranked_battles now has {count} row(s) for `{tag}`.")

    # ---- Step 7: CWL group check -------------------------------------------
    if clan_tag:
        log(f"   Clan tag found: {clan_tag} — run `/force_cwl_pull {tag}` to process wars.")
    else:
        log("   No active clan tag cached for this player, so they cannot be included in CWL polling.")

    # ---- Done ---------------------------------------------------------------
    # Split output across multiple messages if needed (Discord 2000 char limit)
    chunk, chunks = "", []
    for line in lines:
        if len(chunk) + len(line) + 1 > 1900:
            chunks.append(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        chunks.append(chunk)

    for i, c in enumerate(chunks):
        if i == 0:
            await interaction.followup.send(f"```\n{c}```")
        else:
            await interaction.channel.send(f"```\n{c}```")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)