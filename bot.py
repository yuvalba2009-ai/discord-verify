import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp

# Config
TOKEN = os.environ['DISCORD_TOKEN']
GUILD_ID = int(os.environ['GUILD_ID'])
ROLE_ID = int(os.environ['ROLE_ID'])
REQUIRED_BIO = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG = os.environ.get('REQUIRED_TAG', 'BACK')
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
CLIENT_ID = os.environ['CLIENT_ID']
REDIRECT_URI = os.environ['REDIRECT_URI']

authorized_users = set()

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
        self.add_item(discord.ui.Button(label='1. Authorize', style=discord.ButtonStyle.link, url=oauth_url))

    @discord.ui.button(label='2. Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first.", ephemeral=True)

        # Note: Standard Bot tokens cannot see "Bio" or "Clan Tags" for all users 
        # unless the user is in a guild with the bot.
        member = interaction.guild.get_member(interaction.user.id)
        
        # This part requires the bot to have 'Member Profiles' / 'Intents.members'
        # Verification Logic
        bio_content = "" # Bio is restricted in standard API, but we check what's available
        
        # Logic for verification
        # Due to API restrictions, bots usually check 'Activity' or 'Custom Status'
        # If your bot is a "Clan" bot, it can access 'member.clan'
        
        has_bio = REQUIRED_BIO.lower() in (getattr(member, 'description', '') or "").lower()
        # Specific check for Clan Tag if available in your discord.py version
        has_tag = False
        if hasattr(member, 'clan') and member.clan:
            has_tag = member.clan.tag.upper() == REQUIRED_TAG.upper()

        if has_bio and has_tag:
            role = interaction.guild.get_role(ROLE_ID)
            await member.add_roles(role)
            await interaction.followup.send("✅ Verified! Role added.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Verification failed. Ensure bio has `{REQUIRED_BIO}` and Tag is `{REQUIRED_TAG}`.", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())

bot = MyBot()

@bot.tree.command(name='setup-verification', description='Setup the verification portal')
@app_commands.checks.has_permissions(administrator=True)
async def setup_verification(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=f"Follow these steps:\n1. Click **Authorize**\n2. Set bio to: `{REQUIRED_BIO}`\n3. Equp Tag: `{REQUIRED_TAG}`\n4. Click **Verify Me**",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Portal Created!", ephemeral=True)

# Internal API for server.py to talk to bot.py
async def oauth_callback_handler(request):
    if request.headers.get('X-Internal-Secret') != INTERNAL_SECRET:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    authorized_users.add(int(data['user_id']))
    return web.json_response({'success': True})

async def main():
    # Start Internal Server
    app = web.Application()
    app.router.add_post('/internal/oauth-callback', oauth_callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8081).start()
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
