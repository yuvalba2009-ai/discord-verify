import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp

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
        oauth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify"
        self.add_item(discord.ui.Button(label='Authorize', style=discord.ButtonStyle.link, url=oauth_url, emoji='🔑'))

    @discord.ui.button(label='Verify Me', style=discord.ButtonStyle.green, custom_id='verify_me', emoji='✅')
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id not in authorized_users:
            return await interaction.followup.send("❌ Please click **Authorize** first.", ephemeral=True)

        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
            
            # --- Check Status (Bio) ---
            bio_ok = False
            for act in member.activities:
                # Custom Statuses use .state, Game activities use .name
                act_name = str(getattr(act, 'name', '')).lower()
                act_state = str(getattr(act, 'state', '')).lower()
                
                if REQUIRED_BIO.lower() in act_name or REQUIRED_BIO.lower() in act_state:
                    bio_ok = True
                    break
            
            # --- Check Clan Tag ---
            tag_ok = False
            clan = getattr(member, 'clan', None)
            if clan and hasattr(clan, 'tag') and str(clan.tag).upper() == REQUIRED_TAG.upper():
                tag_ok = True
            elif f"[{REQUIRED_TAG.upper()}]" in member.display_name.upper():
                tag_ok = True

            # --- Final Verification ---
            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                if role:
                    await member.add_roles(role)
                    authorized_users.discard(interaction.user.id)
                    await interaction.followup.send("✅ Verified! Role added.", ephemeral=True)
                else:
                    await interaction.followup.send("⚠️ Role ID not found.", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Verification Failed:\n"
                    f"{'✅' if bio_ok else '❌'} Status matches `{REQUIRED_BIO}`\n"
                    f"{'✅' if tag_ok else '❌'} Tag matches `{REQUIRED_TAG}`", 
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents(members=True, presences=True, guilds=True))

    async def setup_hook(self):
        self.add_view(VerifyView())
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))


bot = MyBot()

async def handle_callback(request):
    code = request.query.get('code')
    if not code: return web.Response(text="No code", status=400)
    
    async with aiohttp.ClientSession() as session:
        data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        async with session.post('https://discord.com/api/v10/oauth2/token', data=data) as resp:
            token_data = await resp.json()
        
        headers = {'Authorization': f"Bearer {token_data['access_token']}"}
        async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as resp:
            user_data = await resp.json()
            authorized_users.add(int(user_data['id']))

    return web.Response(text="<html><body style='background:#0e0f13;color:white;text-align:center;padding-top:100px;'><h1>✅ Authorized!</h1><p>Close this tab and click Verify Me.</p><script>setTimeout(window.close, 3000);</script></body></html>", content_type='text/html')

async def main():
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080))).start()
    
    async with bot: await bot.start(TOKEN)


@bot.tree.command(name='setup-verify', description='Deploy portal')
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Server Verification",
        description=f"1. Click **Authorize**\n2. Set Status to `{REQUIRED_BIO}`\n3. Equip Clan Tag `{REQUIRED_TAG}`\n4. Click **Verify Me**",
        color=0x57F287
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Deployed.", ephemeral=True)

if __name__ == '__main__':
    asyncio.run(main())
