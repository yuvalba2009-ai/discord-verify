import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os

# --- Configuration ---
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
        # Removed the "1." from label
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first.", ephemeral=True)

        # Force a fresh fetch of the member to see the newest profile data/tags
        try:
            guild = interaction.guild
            member = await guild.fetch_member(interaction.user.id)
            
            # Check Custom Status (Bio)
            bio_ok = False
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity):
                    if activity.name and REQUIRED_BIO.lower() in activity.name.lower():
                        bio_ok = True
                        break
            
            # Check Clan Tag
            tag_ok = False
            # Some versions of discord.py use member.clan, others might store it in public_flags
            if hasattr(member, 'clan') and member.clan:
                if member.clan.tag.upper() == REQUIRED_TAG.upper():
                    tag_ok = True

            if bio_ok and tag_ok:
                role = guild.get_role(ROLE_ID)
                await member.add_roles(role)
                authorized_users.discard(interaction.user.id)
                await interaction.followup.send("✅ Success! Welcome to the server.", ephemeral=True)
            else:
                msg = "Verification failed:\n"
                if not bio_ok: msg += f"- Add `{REQUIRED_BIO}` to your Custom Status.\n"
                if not tag_ok: msg += f"- Equip the `{REQUIRED_TAG}` Clan Tag.\n"
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

@bot.tree.command(name='setup-verify', description='Setup verification')
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=f"1. Click **Authorize**\n2. Set status to `{REQUIRED_BIO}`\n3. Equip `{REQUIRED_TAG}` Tag\n4. Click **Verify Me**",
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Deployed!", ephemeral=True)

async def start_api():
    app = web.Application()
    app.router.add_post('/internal/oauth-callback', lambda r: handle_callback(r))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8081).start()

async def handle_callback(request):
    if request.headers.get('X-Internal-Secret') != INTERNAL_SECRET:
        return web.json_response({'status': 'unauthorized'}, status=401)
    data = await request.json()
    authorized_users.add(int(data['user_id']))
    return web.json_response({'status': 'ok'})

async def main():
    await start_api()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
