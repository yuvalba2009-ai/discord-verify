import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp

# --- Configuration ---
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
CLIENT_ID       = os.environ['CLIENT_ID']
REDIRECT_URI    = os.environ['REDIRECT_URI']

# Simple in-memory set to track who authorized via OAuth
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
        # Button 1: Link to OAuth
        self.add_item(discord.ui.Button(
            label='1. Authorize', 
            style=discord.ButtonStyle.link, 
            url=oauth_url, 
            emoji='🔑'
        ))

    @discord.ui.button(label='2. Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            await interaction.followup.send("❌ Please click **Authorize** first, complete the process in your browser, then come back.", ephemeral=True)
            return

        try:
            member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
            
            # --- Verification Logic ---
            # Note: Fetching 'Bio' via standard Bot API is limited. 
            # Most bots check 'Custom Status' or 'Activities'.
            bio_text = ""
            if member.activities:
                for activity in member.activities:
                    if isinstance(activity, discord.CustomActivity):
                        bio_text = str(activity.name or "")
            
            bio_ok = REQUIRED_BIO.lower() in bio_text.lower()
            
            # Clan Tag Check (Supported in latest discord.py versions)
            tag_ok = False
            if hasattr(member, 'clan') and member.clan:
                tag_ok = member.clan.tag.upper() == REQUIRED_TAG.upper()

            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                await member.add_roles(role)
                authorized_users.discard(interaction.user.id) # Clean up
                await interaction.followup.send("✅ Verification successful! You have been granted the role.", ephemeral=True)
            else:
                issues = []
                if not bio_ok: issues.append(f"❌ Custom Status must contain `{REQUIRED_BIO}`")
                if not tag_ok: issues.append(f"❌ You must equip the `{REQUIRED_TAG}` clan tag")
                await interaction.followup.send("\n".join(issues), ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ Error during verification: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        intents.presences = True # Required to read Custom Status/Bio
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())
        # Manual sync to the specific guild to bypass the AttributeError
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Commands synced to guild {GUILD_ID}")

bot = MyBot()

@bot.tree.command(name='setup-verify', description='Setup the verification portal')
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=(
            f"To access the server, please follow these steps:\n\n"
            f"1️⃣ Click **Authorize** to link your account.\n"
            f"2️⃣ Add `{REQUIRED_BIO}` to your **Custom Status**.\n"
            f"3️⃣ Equip the `{REQUIRED_TAG}` **Clan Tag**.\n"
            f"4️⃣ Click **Verify Me** below."
        ),
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Verification portal deployed.", ephemeral=True)

# --- Background API for server.py to notify the bot ---
async def oauth_callback_handler(request):
    if request.headers.get('X-Internal-Secret') != INTERNAL_SECRET:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    data = await request.json()
    user_id = int(data.get('user_id'))
    authorized_users.add(user_id)
    print(f"📡 Bot received authorization for User ID: {user_id}")
    return web.json_response({'success': True})

async def start_internal_api():
    app = web.Application()
    app.router.add_post('/internal/oauth-callback', oauth_callback_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    # Bot listens on 8081; Server.py sends to this port
    await web.TCPSite(runner, '0.0.0.0', 8081).start()
    print("🔌 Internal Bot API running on port 8081")

async def main():
    await start_internal_api()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
