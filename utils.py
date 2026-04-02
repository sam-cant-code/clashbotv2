import discord
from discord import app_commands
import aiohttp
import asyncio
import json
import logging
import contextlib
import datetime
import config

logger = logging.getLogger('CoCBot')

# --- NON-BLOCKING FILE HELPERS ---
async def load_json_file(filepath, default):
    def _read():
        try:
            with open(filepath, 'r') as file:
                data = json.load(file)
                if not isinstance(data, type(default)): return default
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return default
    return await asyncio.to_thread(_read)

async def save_json_file(filepath, data):
    def _write():
        with open(filepath, 'w') as file:
            json.dump(data, file, indent=4)
    await asyncio.to_thread(_write)

async def update_bot_state(bot):
    cfg = await load_json_file(config.CONFIG_FILE, {})
    cfg["last_refresh_time"] = bot.last_refresh_time
    cfg["lb_pages"] = {str(k): v for k, v in bot.lb_pages.items()}
    cfg["manual_lb_messages"] = {str(k): v for k, v in bot.manual_lb_messages.items()}
    await save_json_file(config.CONFIG_FILE, cfg)

# --- MATH & FORMATTING HELPERS ---
def format_name_strict(name, max_width=10):
    safe_name = name.replace('`', "'")
    if len(safe_name) > max_width:
        safe_name = safe_name[:max_width - 2] + ".."
    return safe_name.ljust(max_width, ' ')

def calc_legend_trophies(stars, destruction):
    if stars == 0: return destruction // 10
    elif stars == 1: return 5 + max(0, destruction - 1) // 9
    elif stars == 2: return 16 + max(0, destruction - 50) // 3
    elif stars == 3: return 40
    return 0

def to_superscript(num):
    sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
    return ''.join(sup_map.get(char, '') for char in str(num))

def get_delta_str(tag, current_trophies, cache):
    if tag not in cache: return ""
    cached_val = cache[tag]
    if not isinstance(cached_val, int): return ""
    diff = current_trophies - cached_val
    if diff > 0: return f" `▲ +{diff}`"
    if diff < 0: return f" `▼ {diff}`"
    return ""

def get_league_emoji(league_name: str) -> str:
    return config.LEAGUE_EMOJIS.get(league_name, "➖")

def get_league_weight(league_name: str) -> int:
    return config.LEAGUE_WEIGHTS.get(league_name, 0)

def get_battle_sig(b):
    return f"{b.get('opponentPlayerTag')}_{b.get('attack')}_{b.get('stars')}_{b.get('destructionPercentage')}"

# --- PERMISSION CHECK ---
def is_admin_or_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == config.OWNER_ID: return True
        if not interaction.guild: return False
        if interaction.user.guild_permissions.administrator: return True
        return False
    return app_commands.check(predicate)

# --- REUSABLE API FETCH LOGIC ---
async def safe_fetch(session, url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=headers, timeout=10) as r:
                if r.status == 429:
                    delay = 2 ** attempt
                    logger.warning(f"Rate limited (429) on API. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                data = None
                if r.status == 200:
                    data = await r.json()
                return r.status, data
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Network error on fetch: {e}")
            await asyncio.sleep(1)
    return None, None

async def fetch_joke(session):
    url = "https://v2.jokeapi.dev/joke/Dark"
    status, data = await safe_fetch(session, url, {})
    if status == 200 and data:
        if data.get("type") == "twopart":
            return f"{data.get('setup')}\n\n||{data.get('delivery')}||"
        else:
            return data.get("joke")
    return "i cant think of any jokes rn lol 💀🐦"

async def fetch_league_history(session, tag, headers):
    hist_url = f"https://api.clashofclans.com/v1/players/%23{tag}/leaguehistory"
    status, hist_data = await safe_fetch(session, hist_url, headers)
    l_name = "Unranked"
    if status == 200 and hist_data:
        items = hist_data.get('items', [])
        if items:
            latest_item = sorted(items, key=lambda x: str(x.get('season', '')))[-1]
            tier_id = latest_item.get('leagueTierId', 0)
            l_name = config.TIER_ID_TO_NAME.get(tier_id, "Unranked")
    elif status != 200 and status is not None:
        logger.warning(f"History API returned {status} for #{tag}. Falling back to Unranked.")
    return l_name

async def fetch_player_data(session, tag, headers, trophy_cache, legend_stats_cache, semaphore=None):
    async with (semaphore or contextlib.nullcontext()):
        await asyncio.sleep(0.1)
        url = f"https://api.clashofclans.com/v1/players/%23{tag}"
        status, d = await safe_fetch(session, url, headers)
        
        if status == 200 and d:
            th = d.get('townHallLevel', 1)
            current_trophies = d.get('trophies', 0)
            await asyncio.sleep(0.1)
            
            league_tier_id = d.get('leagueTier', {}).get('id')
            if league_tier_id and league_tier_id in config.TIER_ID_TO_NAME:
                l_name = config.TIER_ID_TO_NAME[league_tier_id]
            else:
                league_obj = d.get('leagueTier') or d.get('league') or {}
                l_name = league_obj.get('name', 'Unranked')

            if l_name == "Unranked":
                l_name = await fetch_league_history(session, tag, headers)
                
            weight = get_league_weight(l_name)
            legend_log = None
            
            if weight == 34:  
                if tag not in legend_stats_cache:
                    legend_stats_cache[tag] = {
                        "seen_battles": [], "initialized": False,
                        "off_count": 0, "off_trophies": 0,
                        "def_count": 0, "def_trophies": 0,
                        "last_reset": None
                    }
                
                p_stats = legend_stats_cache[tag]
                now = datetime.datetime.now(datetime.timezone.utc)
                if now.hour >= 5: current_day = now.date()
                else: current_day = (now - datetime.timedelta(days=1)).date()
                current_day_str = current_day.isoformat()

                if p_stats.get("last_reset") != current_day_str:
                    p_stats["off_count"] = 0; p_stats["off_trophies"] = 0
                    p_stats["def_count"] = 0; p_stats["def_trophies"] = 0
                    p_stats["seen_battles"] = []
                    p_stats["initialized"] = False
                    p_stats["last_reset"] = current_day_str
                    logger.info(f"🔄 [{tag}] New Legend Day! Stats reset to 0.")

                log_url = f"https://api.clashofclans.com/v1/players/%23{tag}/battlelog"
                log_status, log_data = await safe_fetch(session, log_url, headers)
                
                if log_status == 403:
                    legend_log = "private"
                elif log_status == 200 and log_data:
                    items = log_data.get('items', [])
                    legend_battles = [b for b in items if b.get('battleType') == 'legend']
                    
                    if not p_stats.get("initialized"):
                        p_stats["seen_battles"] = [get_battle_sig(b) for b in legend_battles]
                        p_stats["initialized"] = True
                    else:
                        new_battles = []
                        seen_set = set(p_stats.get("seen_battles", []))
                        for b in legend_battles:
                            sig = get_battle_sig(b)
                            if sig not in seen_set: new_battles.append(b)
                        
                        if new_battles:
                            for b in reversed(new_battles):
                                sig = get_battle_sig(b)
                                is_attack = b.get('attack', False)
                                stars = b.get('stars', 0)
                                dest = b.get('destructionPercentage', 0)
                                trophies = calc_legend_trophies(stars, dest)
                                
                                if is_attack:
                                    if p_stats["off_count"] < 8:
                                        p_stats["off_trophies"] += trophies
                                        p_stats["off_count"] += 1
                                else:
                                    if p_stats["def_count"] < 8:
                                        if stars == 0: trophies = 0
                                        p_stats["def_trophies"] += trophies
                                        p_stats["def_count"] += 1
                                p_stats["seen_battles"].append(sig)
                            p_stats["seen_battles"] = p_stats["seen_battles"][-20:]

                if legend_log != "private":
                    legend_log = {
                        'off_count': p_stats['off_count'], 'off_trophies': p_stats['off_trophies'],
                        'def_count': p_stats['def_count'], 'def_trophies': p_stats['def_trophies']
                    }

            player_dict = {
                'name':          discord.utils.escape_markdown(d.get('name', 'Unknown')),
                'trophies':      current_trophies,
                'emoji':         get_league_emoji(l_name),
                'league_weight': weight,
                'th':            th,
                'tag':           tag,
                'delta':         get_delta_str(tag, current_trophies, trophy_cache),
                'legend_log':    legend_log
            }
            return player_dict, tag, current_trophies, d
        else:
            logger.warning(f"Profile API returned {status} for #{tag}.")
        return None, tag, None, None