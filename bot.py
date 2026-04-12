import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os

# ============================================================
#  All secrets loaded from environment variables — safe for public GitHub
# ============================================================
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
VERIFY_URL      = os.environ['VERIFY_URL']
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
# ============================================================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label='Verify Me',
            style=discord.ButtonStyle.link,
            emoji='✅',
            url=VERIFY_URL
        ))


@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Sync error: {e}')
    print(f'🤖 Logged in as {bot.user}')


async def assign_role_handler(request):
    secret = request.headers.get('X-Internal-Secret')
    if secret != INTERNAL_SECRET:
        return web.json_response({'error': 'Unauthorized'}, status=401)

    data = await request.json()
    user_id = int(data['user_id'])

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return web.json_response({'error': 'Guild not found'}, status=404)

    member = guild.get_member(user_id) or await guild.fetch_member(user_id)
    if not member:
        return web.json_response({'error': 'Member not found'}, status=404)

    role = guild.get_role(ROLE_ID)
    await member.add_roles(role)
    return web.json_response({'success': True})


async def start_internal_server():
    app = web.Application()
    app.router.add_post('/internal/assign-role', assign_role_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()
    print('🔌 Internal API running on port 8081')


@bot.tree.command(
    name='setup-verify',
    description='Posts the verification button in this channel (admin only)',
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title='✅ Verification',
        description=(
            f'To get verified you need **both** of the following:\n\n'
            f'**1.** Add **`{REQUIRED_BIO}`** to your profile bio\n'
            f'**2.** Have the **`{REQUIRED_TAG}`** clan tag equipped\n\n'
            f'Once done, click the button below!'
        ),
        color=0x5865F2
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message('✅ Verification message posted!', ephemeral=True)


@setup_verify.error
async def setup_verify_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            '❌ You need **Manage Roles** permission to do this.', ephemeral=True
        )


async def main():
    await start_internal_server()
    await bot.start(TOKEN)

asyncio.run(main())
