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
CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
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
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first.", ephemeral=True)

        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
            
            # Check Custom Status
            bio_ok = any(
                isinstance(a, discord.CustomActivity) and REQUIRED_BIO.lower() in str(a.name or "").lower()
                for a in member.activities
            )
            
            # Check Clan Tag
            tag_ok = hasattr(member, 'clan') and member.clan and str(member.clan.tag).upper() == REQUIRED_TAG.upper()

            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                await member.add_roles(role)
                authorized_users.discard(interaction.user.id)
                await interaction.followup.send("✅ Success! Role granted.", ephemeral=True)
            else:
                msg = "Verification Failed:\n"
                msg += f"{'✅' if bio_ok else '❌'} Status: `{REQUIRED_BIO}`\n"
                msg += f"{'✅' if tag_ok else '❌'} Clan Tag: `{REQUIRED_TAG}`"
                await interaction.followup.send(msg, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        intents.presences = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))

bot = MyBot()

# --- Combined Web Server (Handles the Redirect) ---
async def handle_callback(request):
    code = request.query.get('code')
    if not code:
        return web.Response(text="No code provided", status=400)

    # Exchange code for token
    async with aiohttp.ClientSession() as session:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        async with session.post('https://discord.com/api/v10/oauth2/token', data=data) as resp:
            if resp.status != 200:
                return web.Response(text="Token exchange failed", status=400)
            token_data = await resp.json()
            
        # Get User ID
        headers = {'Authorization': f"Bearer {token_data['access_token']}"}
        async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as resp:
            user_data = await resp.json()
            user_id = int(user_data['id'])
            authorized_users.add(user_id)

    return web.Response(text="""
        <html><body style="background:#0e0f13;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
            <h1 style="color:#57F287;">✅ Authorized!</h1>
            <p>You can close this tab and click <b>Verify Me</b> in Discord.</p>
            <script>setTimeout(function(){ window.close(); }, 3000);</script>
        </body></html>
    """, content_type='text/html')

async def main():
    # Start the web server on the port Railway provides
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()
    
    async with bot:
        await bot.start(TOKEN)

@bot.tree.command(name='setup-verify', description='Deploy portal')
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def setup_verify(interaction: discord.Interaction):
    await interaction.channel.send(view=VerifyView())
    await interaction.response.send_message("Deployed.", ephemeral=True)

if __name__ == '__main__':
    asyncio.run(main())
