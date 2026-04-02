import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging
from collections import defaultdict
from better_profanity import profanity
import config
from utils import load_json_file

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger('CoCBot')

profanity.load_censor_words()
profanity.add_censor_words(["idiot", "dumb", "moron", "loser", "kys", "stfu"])

class CoCBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.session = None
        self.last_refresh_time = 0.0
        self.manual_lb_messages = {}
        self.lb_pages = {}
        
        self.user_data = defaultdict(lambda: {
            "messages": [], "caps_times": [], "swear_times": [], "chaos_times": [],
            "last_trigger": 0, "last_bot_response": "", "last_interaction": 0,
            "mood": "friendly", "grudge_score": 0, "goodnight_time": 0,
            "history": [], "mentioned_topics": set(), "bad_word_count": 0
        })

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        cfg = await load_json_file(config.CONFIG_FILE, {})
        self.last_refresh_time = cfg.get("last_refresh_time", 0.0)
        self.lb_pages = {int(k): v for k, v in cfg.get("lb_pages", {}).items()}
        self.manual_lb_messages = {int(k): v for k, v in cfg.get("manual_lb_messages", {}).items()}
        
        await self.load_extension('cogs.admin')
        await self.load_extension('cogs.leaderboard')
        await self.load_extension('cogs.chat')
        
        await self.tree.sync()

    async def close(self):
        if self.session: await self.session.close()
        await super().close()

bot = CoCBot()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} with Modular Cogs!')
    if config.OWNER_ID == 0: logger.warning("OWNER_ID missing or 0. Permissions may fail.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("⛔ You do not have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"App command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

if __name__ == '__main__':
    bot.run(config.DISCORD_TOKEN)