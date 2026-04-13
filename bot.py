import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os

# Config
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
CLIENT_ID       = os.environ['CLIENT_ID']
REDIRECT_URI    = os.environ['REDIRECT_URI']

authorized_users = set()

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        oauth_url = (
            f"https://discord.com/oauth2/authorize"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=code"
            f"&scope=identify"
        )
        self.add_item(discord.ui.Button(label='1. Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='2. Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first, then come back and click this.", ephemeral=True)

        member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
        
        # Check Bio (Note: requires Intents.members)
        # Note: 'about_me' isn't always available via Bot API directly, 
        # but we check if it's in the member's activity/status or available fields.
        bio_ok = REQUIRED_BIO.lower() in (getattr(member, 'status', '') or "").lower() 
        
        # Check Clan Tag (Requires latest discord.py version)
        tag_ok = False
        if hasattr(member, 'clan') and member.clan:
            tag_ok = member.clan.tag.upper() == REQUIRED_TAG.upper()

        if bio_ok and tag_ok:
            role = interaction.guild.get_role(ROLE_ID)
            await member.add_roles(role)
            await interaction.followup.send("✅ Verification successful! Role granted.", ephemeral=True)
        else:
            await interaction.followup.send(
                f"❌ Verification failed.\n- Bio must contain: `{REQUIRED_BIO}`\n- Tag must be: `{REQUIRED_TAG}`", 
                ephemeral=True
            )

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Register the persistent view so it works after bot restarts
        self.add_view(VerifyView())
        # Syncing commands to your specific guild (faster than global sync)
        self.tree.copy_from(guild=discord.Object(id=GUILD_ID))
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))

bot = MyBot()

@bot.tree.command(name='setup-verify', description='Setup the verification portal')
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    # This responds IMMEDIATELY to prevent "Application did not respond"
    await interaction.response.send_message("Creating portal...", ephemeral=True)
    
    embed = discord.Embed(
        title="Verification System",
        description=(
            f"To gain access, you must:\n\n"
            f"1. Add `{REQUIRED_BIO}` to your bio.\n"
            f"2. Have the `{REQUIRED_TAG}` clan tag.\n\n"
            "Click the buttons below in order."
        ),
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=VerifyView())

# --- Background Server for OAuth ---
async def oauth_callback_handler(request):
    if request.headers.get('X-Internal-Secret') != INTERNAL_SECRET:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    data = await request.json()
    authorized_users.add(int(data['user_id']))
    return web.json_response({'success': True})

async def start_background_server():
    app = web.Application()
    app.router.add_post('/internal/oauth-callback', oauth_callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()

async def main():
    await start_background_server()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
