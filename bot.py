import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp

# --- Configuration (Pulled from Railway Variables) ---
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']

# Simple set to track users who completed the browser step
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
        # Clean buttons without numbers
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first and complete the browser steps.", ephemeral=True)

        try:
            # fetch_member forces the bot to get the freshest data from Discord's API
            member = await interaction.guild.fetch_member(interaction.user.id)
            
            # 1. Check Custom Status (Bio)
            bio_ok = False
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity):
                    if activity.name and REQUIRED_BIO.lower() in str(activity.name).lower():
                        bio_ok = True
                        break
            
            # 2. Check Clan Tag (Targeting the member.clan attribute)
            tag_ok = False
            if hasattr(member, 'clan') and member.clan:
                if str(member.clan.tag).upper() == REQUIRED_TAG.upper():
                    tag_ok = True

            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                if role:
                    await member.add_roles(role)
                    authorized_users.discard(interaction.user.id)
                    await interaction.followup.send("✅ Everything matches! You have been verified.", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ Error: Role not found. Check ROLE_ID in Railway.", ephemeral=True)
            else:
                # Direct feedback to help you troubleshoot
                msg = "Verification Failed:\n"
                msg += f"{'✅' if bio_ok else '❌'} Custom Status: must contain `{REQUIRED_BIO}`\n"
                msg += f"{'✅' if tag_ok else '❌'} Clan Tag: must be `{REQUIRED_TAG}`"
                await interaction.followup.send(msg, ephemeral=True)

        except Exception as e:
            print(f"Error in verify_me: {e}")
            await interaction.followup.send(f"⚠️ Failed to read profile. Error: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        intents.presences = True # CRITICAL: Must be enabled in Developer Portal
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())
        # Forces the slash command to sync to your specific server
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Commands synced and view active.")

bot = MyBot()

# --- Unified Web Server ---
# This part replaces server.py and listens for the Discord redirect
async def handle_callback(request):
    code = request.query.get('code')
    if not code:
        return web.Response(text="No authorization code.", status=400)

    async with aiohttp.ClientSession() as session:
        # Swap code for Token
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
            
        # Get the User ID
        user_headers = {'Authorization': f"Bearer {token_data['access_token']}"}
        async with session.get('https://discord.com/api/v10/users/@me', headers=user_headers) as resp:
            user_info = await resp.json()
            user_id = int(user_info['id'])
            authorized_users.add(user_id)

    # Self-closing professional success page
    return web.Response(text="""
        <html><body style="background:#0e0f13;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
            <h1 style="color:#57F287;font-size:48px;">✅ Authorized!</h1>
            <p style="font-size:20px;">You can close this tab and return to Discord.</p>
            <script>setTimeout(function(){ window.close(); }, 3000);</script>
        </body></html>
    """, content_type='text/html')

@bot.tree.command(name='setup-verify', description='Deploys the verification message')
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Verification Portal",
        description=(
            f"1. Click **Authorize**\n"
            f"2. Set Custom Status to: `{REQUIRED_BIO}`\n"
            f"3. Equip Clan Tag: `{REQUIRED_TAG}`\n"
            "4. Click **Verify Me**"
        ),
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Portal deployed!", ephemeral=True)

async def main():
    # Start the web server for the callback
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    # Railway provides the PORT automatically
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    print(f"🔌 Web server listening on port {port}")
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
