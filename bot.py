import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp

# --- Configuration (Pulled from Railway Environment Variables) ---
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']

# In-memory tracking for users who finished the browser authorization
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
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first and complete the steps in your browser.", ephemeral=True)

        try:
            # fetch_member bypasses local cache to get fresh status data from Discord
            member = await interaction.guild.fetch_member(interaction.user.id)
            
            # Debug log to Railway console - if this list is empty, Intents are OFF in portal
            print(f"DEBUG: Checking {member.name}. Activities: {member.activities}")
            
            bio_ok = False
            if member.activities:
                for activity in member.activities:
                    # Check standard Custom Status or fallback to any activity name (Playing/Status)
                    if isinstance(activity, discord.CustomActivity) or hasattr(activity, 'name'):
                        act_name = str(activity.name or "").lower()
                        if REQUIRED_BIO.lower() in act_name:
                            bio_ok = True
                            break

            if bio_ok:
                role = interaction.guild.get_role(ROLE_ID)
                if role:
                    await member.add_roles(role)
                    authorized_users.discard(interaction.user.id)
                    await interaction.followup.send(f"✅ Verified! The role has been added to your profile.", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ Error: Role ID not found. Ensure ROLE_ID in Railway is correct.", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Could not find `{REQUIRED_BIO}` in your Custom Status.\n\n"
                    "**How to fix:**\n"
                    "1. Go to **Set Custom Status** (not your 'About Me' bio).\n"
                    "2. Ensure your status is **Online** (Green circle).\n"
                    "3. Try removing and re-adding the status.", ephemeral=True)

        except Exception as e:
            print(f"VERIFY ERROR: {e}")
            await interaction.followup.send(f"⚠️ Error reading profile: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        intents.presences = True # REQUIRES TOGGLE IN DEV PORTAL
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())
        # Manual sync to your specific guild ID
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Bot is ready and commands are synced to guild {GUILD_ID}")

bot = MyBot()

# --- Internal Web Server (Handles Redirect from Browser) ---
async def handle_callback(request):
    code = request.query.get('code')
    if not code:
        return web.Response(text="No authorization code provided.", status=400)

    async with aiohttp.ClientSession() as session:
        # Swap code for Access Token
        token_url = 'https://discord.com/api/v10/oauth2/token'
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        async with session.post(token_url, data=data) as resp:
            if resp.status != 200:
                return web.Response(text="Token exchange failed.", status=400)
            token_data = await resp.json()
            
        # Use token to get User ID
        user_headers = {'Authorization': f"Bearer {token_data['access_token']}"}
        async with session.get('https://discord.com/api/v10/users/@me', headers=user_headers) as resp:
            user_info = await resp.json()
            user_id = int(user_info['id'])
            authorized_users.add(user_id)

    # Browser page that tells user to go back to Discord
    return web.Response(text="""
        <html><body style='background:#0e0f13;color:white;text-align:center;padding-top:100px;font-family:sans-serif;'>
            <h1 style='color:#57F287;font-size:48px;'>✅ Authorized!</h1>
            <p style='font-size:20px;'>Close this tab and click <b>Verify Me</b> in Discord.</p>
            <script>setTimeout(function(){ window.close(); }, 3000);</script>
        </body></html>
    """, content_type='text/html')

async def main():
    # Setup the web server to run alongside the bot
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Railway provides the PORT env variable automatically
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    print(f"🔌 Web server (OAuth) listening on port {port}")
    
    async with bot:
        await bot.start(TOKEN)

@bot.tree.command(name='setup-verify', description='Deploys the verification message')
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=f"To gain access, please:\n1. Click **Authorize**\n2. Add `{REQUIRED_BIO}` to your Status\n3. Click **Verify Me**",
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Verification message deployed.", ephemeral=True)

if __name__ == '__main__':
    asyncio.run(main())
