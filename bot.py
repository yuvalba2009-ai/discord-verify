import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web
import asyncio
import os
import aiohttp
import time

# --- Configuration ---
TOKEN           = os.environ['DISCORD_TOKEN']
GUILD_ID        = int(os.environ['GUILD_ID'])
ROLE_ID         = int(os.environ['ROLE_ID'])
LOG_CHANNEL_ID  = int(os.environ['LOG_CHANNEL_ID']) # <-- NEW VARIABLE
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
            cached_member = interaction.guild.get_member(interaction.user.id) or interaction.user
            api_member = await interaction.guild.fetch_member(interaction.user.id)
            
            # Check Status (Bio)
            bio_ok = False
            for act in cached_member.activities:
                act_name = str(getattr(act, 'name', '')).lower()
                act_state = str(getattr(act, 'state', '')).lower()
                if REQUIRED_BIO.lower() in act_name or REQUIRED_BIO.lower() in act_state:
                    bio_ok = True
                    break
            
            # Check Clan Tag
            tag_ok = False
            clan = getattr(api_member, 'clan', None)
            if clan and hasattr(clan, 'tag') and str(clan.tag).upper() == REQUIRED_TAG.upper():
                tag_ok = True
            
            if not tag_ok:
                try:
                    route = discord.http.Route('GET', f'/guilds/{interaction.guild.id}/members/{interaction.user.id}')
                    raw_data = await interaction.client.http.request(route)
                    if "'tag':" in str(raw_data).lower() and REQUIRED_TAG.lower() in str(raw_data).lower():
                        tag_ok = True
                except Exception:
                    pass

            if not tag_ok and f"[{REQUIRED_TAG.upper()}]" in api_member.display_name.upper():
                tag_ok = True

            # Final Action
            if bio_ok and tag_ok:
                role = interaction.guild.get_role(ROLE_ID)
                if role:
                    await api_member.add_roles(role)
                    authorized_users.discard(interaction.user.id)
                    await interaction.followup.send("✅ Verified! Welcome to the server.", ephemeral=True)
                    
                    # --- LOGGING: ROLE ASSIGNED ---
                    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
                    if log_channel:
                        current_time = int(time.time())
                        await log_channel.send(f"✅ Role assigned to {api_member.mention} at <t:{current_time}:t>")

                else:
                    await interaction.followup.send("⚠️ Role ID not found.", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Verification Failed:\n"
                    f"{'✅' if bio_ok else '❌'} Status matches `{REQUIRED_BIO}`\n"
                    f"{'✅' if tag_ok else '❌'} Clan Tag matches `{REQUIRED_TAG}`", 
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents(members=True, presences=True, guilds=True))
        self.maintenance_locks = set()

    async def setup_hook(self):
        self.add_view(VerifyView())
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Bot is online and synced.")

    async def check_maintenance(self, member):
        if member.bot or member.guild.id != GUILD_ID:
            return

        if member.id in self.maintenance_locks:
            return
        self.maintenance_locks.add(member.id)

        try:
            role = member.guild.get_role(ROLE_ID)
            if not role or role not in member.roles:
                return

            # 1. Check Bio
            bio_ok = False
            for act in member.activities:
                act_name = str(getattr(act, 'name', '')).lower()
                act_state = str(getattr(act, 'state', '')).lower()
                if REQUIRED_BIO.lower() in act_name or REQUIRED_BIO.lower() in act_state:
                    bio_ok = True
                    break

            # 2. Check Tag
            tag_ok = False
            clan = getattr(member, 'clan', None)
            if clan and hasattr(clan, 'tag') and str(clan.tag).upper() == REQUIRED_TAG.upper():
                tag_ok = True
            elif f"[{REQUIRED_TAG.upper()}]" in member.display_name.upper():
                tag_ok = True

            if not tag_ok and bio_ok:
                try:
                    route = discord.http.Route('GET', f'/guilds/{member.guild.id}/members/{member.id}')
                    raw_data = await self.http.request(route)
                    if "'tag':" in str(raw_data).lower() and REQUIRED_TAG.lower() in str(raw_data).lower():
                        tag_ok = True
                except Exception:
                    pass

            # 3. Action
            if not bio_ok or not tag_ok:
                await member.remove_roles(role)
                reason = "Custom Status" if not bio_ok else "Clan Tag"
                
                embed = discord.Embed(
                    title="Verification Removed",
                    description=f"Your verified role in **{member.guild.name}** has been automatically removed.",
                    color=0xED4245
                )
                embed.add_field(name="Reason", value=f"You removed the required `{reason}`.", inline=False)
                embed.add_field(name="How to fix", value="Add it back and click **Verify Me**.\n- Regain the role at <#1493301591036661770>", inline=False)
                
                try:
                    await member.send(embed=embed)
                except discord.Forbidden:
                    print(f"⚠️ Could not DM {member.name}.")

                # --- LOGGING: ROLE REMOVED ---
                log_channel = member.guild.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    current_time = int(time.time())
                    await log_channel.send(f"❌ Role removed from {member.mention} at <t:{current_time}:t> (Reason: Missing {reason})")
                
                await asyncio.sleep(5)

        except Exception as e:
            print(f"Maintenance Error: {e}")
        finally:
            self.maintenance_locks.discard(member.id)

    async def on_presence_update(self, before, after):
        await self.check_maintenance(after)

    async def on_member_update(self, before, after):
        await self.check_maintenance(after)


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

    return web.Response(text="<html><body style='background:#0e0f13;color:white;text-align:center;padding-top:100px;font-family:sans-serif;'><h1>✅ Authorized!</h1><p>Close this tab and click Verify Me in Discord.</p><script>setTimeout(window.close, 3000);</script></body></html>", content_type='text/html')

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
