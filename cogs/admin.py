import discord
from discord.ext import commands
from discord import app_commands
import re
import config
from utils import load_json_file, save_json_file, safe_fetch, is_admin_or_owner

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='add', description="Add a Clash of Clans player to the tracker.")
    @app_commands.describe(player_tag="The in-game tag of the player (with or without #)")
    @is_admin_or_owner()
    async def add_player(self, interaction: discord.Interaction, player_tag: str):
        await interaction.response.defer(ephemeral=True)

        clean_tag = player_tag.strip().lstrip('#').upper()
        if not re.match(r'^[A-Z0-9]+$', clean_tag):
            return await interaction.followup.send("❌ Invalid tag format. Please use only letters and numbers.")

        url = f"https://api.clashofclans.com/v1/players/%23{clean_tag}"
        headers = {'Authorization': f'Bearer {config.COC_TOKEN}'}

        status, data = await safe_fetch(self.bot.session, url, headers)
        
        if status == 200 and data:
            players = await load_json_file(config.PLAYERS_FILE, [])
            if clean_tag not in players:
                players.append(clean_tag)
                await save_json_file(config.PLAYERS_FILE, players)
                await interaction.followup.send(f"✅ Added **{data.get('name')}** to the server tracker!")
            else:
                await interaction.followup.send("⚠️ Player is already in the server tracker.")
        else:
            await interaction.followup.send("❌ Player not found or API is rate-limiting. Double check the tag and try again.")

    @app_commands.command(name='add_clan', description="Add all members of a Clash of Clans clan to the tracker.")
    @app_commands.describe(clan_tag="The in-game tag of the clan (with or without #)")
    @is_admin_or_owner()
    async def add_clan(self, interaction: discord.Interaction, clan_tag: str):
        await interaction.response.defer(ephemeral=True)

        clean_tag = clan_tag.strip().lstrip('#').upper()
        if not re.match(r'^[A-Z0-9]+$', clean_tag):
            return await interaction.followup.send("❌ Invalid clan tag format. Please use only letters and numbers.")

        url = f"https://api.clashofclans.com/v1/clans/%23{clean_tag}"
        headers = {'Authorization': f'Bearer {config.COC_TOKEN}'}

        status, data = await safe_fetch(self.bot.session, url, headers)
        
        if status == 200 and data:
            members = data.get('memberList', [])
            clan_name = data.get('name', 'Unknown Clan')
            players = await load_json_file(config.PLAYERS_FILE, [])
            added_count = 0

            for member in members:
                member_tag = member.get('tag', '').lstrip('#').upper()
                if member_tag and member_tag not in players:
                    players.append(member_tag)
                    added_count += 1

            if added_count > 0:
                await save_json_file(config.PLAYERS_FILE, players)
                await interaction.followup.send(f"✅ Successfully added **{added_count}** new members from **{clan_name}** to the server tracker!")
            else:
                await interaction.followup.send(f"⚠️ All members of **{clan_name}** are already in the tracker.")
        else:
            await interaction.followup.send("❌ Clan not found or API is rate-limiting. Double check the clan tag and try again.")

    @app_commands.command(name='remove', description="Remove a player from the server tracker.")
    @app_commands.describe(player_tag="The in-game tag of the player (with or without #)")
    @is_admin_or_owner()
    async def remove_player(self, interaction: discord.Interaction, player_tag: str):
        await interaction.response.defer(ephemeral=True)

        clean_tag = player_tag.strip().lstrip('#').upper()
        if not re.match(r'^[A-Z0-9]+$', clean_tag):
            return await interaction.followup.send("❌ Invalid tag format.")

        players = await load_json_file(config.PLAYERS_FILE, [])
        if clean_tag in players:
            players.remove(clean_tag)
            await save_json_file(config.PLAYERS_FILE, players)
            await interaction.followup.send(f"🗑️ Removed **#{clean_tag}** from the server tracker.")
        else:
            await interaction.followup.send("⚠️ Player is not currently in the server tracker.")

    @app_commands.command(name='resetpersonality', description="Reset the bot's grudge and mood for a specific user.")
    @app_commands.describe(user="The Discord user to reset")
    @is_admin_or_owner()
    async def reset_personality(self, interaction: discord.Interaction, user: discord.Member):
        if user.id not in self.bot.user_data:
            await interaction.response.send_message(f"⚠️ **{user.display_name}** has no active memory state to reset.", ephemeral=True)
            return

        user_state = self.bot.user_data[user.id]
        user_state["grudge_score"] = 0
        user_state["mood"] = "friendly"
        user_state["bad_word_count"] = 0
        
        await interaction.response.send_message(f"✅ Reset personality state for {user.mention}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))