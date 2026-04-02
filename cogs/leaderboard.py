import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import time
import logging
import config
from utils import load_json_file, save_json_file, update_bot_state, fetch_player_data, format_name_strict, to_superscript, is_admin_or_owner

logger = logging.getLogger('CoCBot')

async def build_leaderboard_embeds(bot):
    players = await load_json_file(config.PLAYERS_FILE, [])
    if not players:
        embed = discord.Embed(
            title=f"{config.TROPHY_EMOJI} Server Leaderboard {config.TROPHY_EMOJI}",
            description="The server leaderboard is empty. Ask an admin to use `/add` or `/add_clan` to track someone.",
            color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Page 1/1 | Last Refreshed")
        return [embed]

    trophy_cache = await load_json_file(config.TROPHY_CACHE_FILE, {})
    legend_stats_cache = await load_json_file(config.LEGEND_STATS_FILE, {})
    
    keys_to_remove = [k for k in legend_stats_cache if k not in players]
    for k in keys_to_remove: del legend_stats_cache[k]
        
    new_cache = {}
    data_list = []
    headers = {'Authorization': f'Bearer {config.COC_TOKEN}'}
    semaphore = asyncio.Semaphore(3)

    fetch_tasks = [fetch_player_data(bot.session, tag, headers, trophy_cache, legend_stats_cache, semaphore) for tag in players]
    results = await asyncio.gather(*fetch_tasks)

    for player_dict, tag, current_trophies, _ in results:
        if player_dict:
            data_list.append(player_dict)
            new_cache[tag] = current_trophies

    await save_json_file(config.TROPHY_CACHE_FILE, new_cache)
    await save_json_file(config.LEGEND_STATS_FILE, legend_stats_cache) 

    data_list.sort(key=lambda x: (x['league_weight'], x['trophies']), reverse=True)
    embeds = []
    chunk_size = 20
    total_pages = max(1, (len(data_list) + chunk_size - 1) // chunk_size)

    for i in range(0, max(1, len(data_list)), chunk_size):
        chunk = data_list[i:i + chunk_size]
        desc = ""
        for j, p in enumerate(chunk, start=i + 1):
            rank_str = f"{j}.".ljust(3)
            display_name = format_name_strict(p['name'], 10)
            trophies_str = f"{p['trophies']:>4}"
            clean_tag = p['tag'].replace('#', '')
            profile_url = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={clean_tag}"
            line = f"`{rank_str}`{p['emoji']} [**`{display_name}`**]({profile_url})**{trophies_str}**{config.TROPHY_EMOJI}"
            
            if p.get('league_weight') == 34:
                ll = p.get('legend_log')
                if ll == "private":
                    line += " | `🔒 Private`"
                elif isinstance(ll, dict):
                    sup_off = to_superscript(ll['off_count'])
                    sup_def = to_superscript(ll['def_count'])
                    off_str = f"+{ll['off_trophies']}{sup_off}".ljust(5)
                    def_str = f"-{ll['def_trophies']}{sup_def}".ljust(5)
                    line += f" | `{off_str}|{def_str}`"
                    
            if p['delta']: line += p['delta']
            desc += line + "\n"

        embed = discord.Embed(
            title=f"{config.TROPHY_EMOJI} Server Leaderboard {config.TROPHY_EMOJI}",
            description=desc, color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        current_page = (i // chunk_size) + 1
        embed.set_footer(text=f"Page {current_page}/{total_pages} | Last Refreshed")
        embeds.append(embed)

    return embeds

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, embeds=None, current_page=0, message_id=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.embeds = embeds
        self.current_page = current_page
        self.message_id = message_id
        self.cooldown_seconds = 300
        if self.embeds: self.update_buttons()

    async def ensure_embeds(self, interaction: discord.Interaction):
        if not self.embeds:
            await interaction.response.defer()
            self.embeds = await build_leaderboard_embeds(self.bot)
            try:
                original_msg = await interaction.channel.fetch_message(interaction.message.id)
                footer = original_msg.embeds[0].footer.text
                page_str = footer.split('|')[0].strip().split(' ')[1]
                self.current_page = int(page_str.split('/')[0]) - 1
            except Exception:
                self.current_page = 0
            self.current_page = min(max(0, self.current_page), len(self.embeds) - 1)
            self.update_buttons()

    def update_buttons(self):
        if self.embeds:
            self.prev_button.disabled = self.current_page <= 0
            self.next_button.disabled = self.current_page >= len(self.embeds) - 1

    async def save_state(self, interaction):
        msg_id = self.message_id or interaction.message.id
        self.bot.lb_pages[msg_id] = self.current_page
        await update_bot_state(self.bot)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="lb_prev_btn")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ensure_embeds(interaction)
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await self.save_state(interaction)
        if interaction.response.is_done(): await interaction.edit_original_response(embed=self.embeds[self.current_page], view=self)
        else: await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄", custom_id="refresh_lb_btn")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = time.time()
        if current_time - self.bot.last_refresh_time < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - (current_time - self.bot.last_refresh_time))
            minutes, seconds = divmod(remaining, 60)
            await interaction.response.send_message(
                f"⏳ The leaderboard was just updated! Please wait **{minutes}m {seconds}s** before refreshing again.", ephemeral=True
            )
            return

        if self.embeds:
            loading_embed = self.embeds[self.current_page].copy()
            loading_embed.set_footer(text="⏳ Fetching latest data from Clash of Clans API, please wait...")
        else:
            loading_embed = discord.Embed(title=f"{config.TROPHY_EMOJI} Server Leaderboard {config.TROPHY_EMOJI}", description="⏳ Fetching latest data from Clash of Clans API, please wait...", color=discord.Color.gold())
        
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=loading_embed, view=self)
        
        self.bot.last_refresh_time = current_time
        new_embeds = await build_leaderboard_embeds(self.bot)
        self.embeds = new_embeds
        self.current_page = min(self.current_page, len(self.embeds) - 1)
        
        for child in self.children: child.disabled = False
        self.update_buttons()
        await self.save_state(interaction)
        await interaction.edit_original_response(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="lb_next_btn")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ensure_embeds(interaction)
        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        self.update_buttons()
        await self.save_state(interaction)
        if interaction.response.is_done(): await interaction.edit_original_response(embed=self.embeds[self.current_page], view=self)
        else: await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(LeaderboardView(self.bot))
        if not self.auto_update_leaderboard.is_running():
            self.auto_update_leaderboard.start()

    def cog_unload(self):
        self.auto_update_leaderboard.cancel()

    @tasks.loop(minutes=5)
    async def auto_update_leaderboard(self):
        cfg = await load_json_file(config.CONFIG_FILE, {})
        channel_id = cfg.get("channel_id")
        message_id = cfg.get("message_id")

        if not channel_id or not message_id: return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try: channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound: return

        if channel:
            try:
                message = await channel.fetch_message(message_id)
                embeds = await build_leaderboard_embeds(self.bot)
                self.bot.last_refresh_time = time.time()
                current = self.bot.lb_pages.get(message_id, 0)
                current = min(current, len(embeds) - 1)
                view = LeaderboardView(self.bot, embeds, current_page=current, message_id=message_id)
                await message.edit(embed=embeds[current], view=view)
                await update_bot_state(self.bot)
                logger.info("Auto-updated background leaderboard successfully.")
            except discord.NotFound:
                logger.warning("Leaderboard message not found. Clearing config.")
                cfg["channel_id"] = None
                cfg["message_id"] = None
                await save_json_file(config.CONFIG_FILE, cfg)
            except Exception as e:
                logger.error(f"Failed to auto-update leaderboard: {e}", exc_info=True)

    @auto_update_leaderboard.before_loop
    async def before_auto_update(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='setleaderboard', description="Set up the automated updating leaderboard in this channel.")
    @is_admin_or_owner()
    async def set_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await load_json_file(config.CONFIG_FILE, {})
        old_channel_id = cfg.get("channel_id")
        old_message_id = cfg.get("message_id")

        if old_channel_id and old_message_id:
            old_channel = self.bot.get_channel(old_channel_id)
            if old_channel:
                try:
                    old_msg = await old_channel.fetch_message(old_message_id)
                    await old_msg.delete()
                except Exception: pass

        embeds = await build_leaderboard_embeds(self.bot)
        self.bot.last_refresh_time = time.time()
        
        view = LeaderboardView(self.bot, embeds)
        lb_message = await interaction.channel.send(embed=embeds[0], view=view)

        view.message_id = lb_message.id
        self.bot.lb_pages[lb_message.id] = 0

        cfg["channel_id"] = interaction.channel_id
        cfg["message_id"] = lb_message.id
        await save_json_file(config.CONFIG_FILE, cfg)
        await update_bot_state(self.bot)

        await interaction.followup.send("✅ Automated leaderboard successfully set up in this channel!", ephemeral=True)

    @app_commands.command(name='leaderboard', description="Manually fetch the current server leaderboard.")
    @app_commands.checks.cooldown(1, 300, key=lambda i: i.guild_id)
    async def command_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if interaction.channel_id in self.bot.manual_lb_messages:
            try:
                old_msg = await interaction.channel.fetch_message(self.bot.manual_lb_messages[interaction.channel_id])
                await old_msg.delete()
            except Exception: pass

        embeds = await build_leaderboard_embeds(self.bot)
        self.bot.last_refresh_time = time.time()
        
        view = LeaderboardView(self.bot, embeds)
        msg = await interaction.followup.send(embed=embeds[0], view=view, wait=True)
        
        self.bot.manual_lb_messages[interaction.channel_id] = msg.id
        view.message_id = msg.id
        self.bot.lb_pages[msg.id] = 0
        await update_bot_state(self.bot)

    @command_leaderboard.error
    async def command_leaderboard_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes, seconds = divmod(int(error.retry_after), 60)
            await interaction.response.send_message(
                f"⏳ The leaderboard command is on cooldown! Try again in **{minutes}m {seconds}s**.", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))