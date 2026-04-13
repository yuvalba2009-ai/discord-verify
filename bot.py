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
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first.", ephemeral=True)

        try:
            # Force a fresh API call to get the newest tag/status
            member = await interaction.guild.fetch_member(interaction.user.id)
            
            # Check Bio (Custom Status)
            bio_ok = False
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity):
                    status_text = str(activity.name or "")
                    if REQUIRED_BIO.lower() in status_text.lower():
                        bio_ok = True
                        break
            
            # Check Clan Tag
            tag_ok = False
            if hasattr(member, 'clan') and member.clan:
                if str(member.clan.tag).upper() == REQUIRED_TAG.upper():
                    tag_ok = True

            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                if role:
                    await member.add_roles(role)
                    authorized_users.discard(interaction.user.id)
                    await interaction.followup.send("✅ Success! The role has been added.", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ Error: Role ID not found. Contact Admin.", ephemeral=True)
            else:
                # Feedback on what is missing
                msg = "Verification Failed:\n"
                msg += f"{'✅' if bio_ok else '❌'} Status/Bio: `{REQUIRED_BIO}`\n"
                msg += f"{'✅' if tag_ok else '❌'} Clan Tag: `{REQUIRED_TAG}`"
                await interaction.followup.send(msg, ephemeral=True)

        except Exception as e:
            print(f"Verify Error: {e}")
            await interaction.followup.send("⚠️ Could not read your profile. Ensure you are 'Online' and try again.", ephemeral=True)

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

@bot.tree.command(name='setup-verify', description='Deploys verification portal')
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=(
            f"1. Click **Authorize**\n"
            f"2. Set Custom Status to `{REQUIRED_BIO}`\n"
            f"3. Equip `{REQUIRED_TAG}` Clan Tag\n"
            "4. Click **Verify Me**"
        ),
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Portal Deployed.", ephemeral=True)

# --- Internal API ---
async def start_api():
    app = web.Application()
    app.router.add_post('/internal/oauth-callback', handle_internal)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8081).start()

async def handle_internal(request):
    if request.headers.get('X-Internal-Secret') != INTERNAL_SECRET:
        return web.json_response({'error': 'unauthorized'}, status=401)
    data = await request.json()
    authorized_users.add(int(data['user_id']))
    return web.json_response({'status': 'ok'})

async def main():
    await start_api()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
