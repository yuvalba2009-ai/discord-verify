from flask import Flask, redirect, request, session
import requests
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ============================================================
CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
BOT_TOKEN       = os.environ['DISCORD_TOKEN']
GUILD_ID        = os.environ['GUILD_ID']
BOT_API_URL     = 'http://localhost:8081/internal/assign-role'
# ============================================================

DISCORD_AUTH_URL  = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_API_BASE  = 'https://discord.com/api/v10'
SCOPES = 'identify'


@app.route('/verify')
def verify():
    """Step 1: Redirect to Discord OAuth"""
    params = (
        f'client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&response_type=code'
        f'&scope={SCOPES}'
    )
    return redirect(f'{DISCORD_AUTH_URL}?{params}')


@app.route('/callback')
def callback():
    """After OAuth: fetch profile, show Step 2 confirm page"""
    code = request.args.get('code')
    if not code:
        return render_result(False, 'No authorization code received.')

    # Exchange code for access token
    token_resp = requests.post(DISCORD_TOKEN_URL, data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'})

    if token_resp.status_code != 200:
        return render_result(False, 'Failed to get access token from Discord.')

    access_token = token_resp.json()['access_token']
    user_headers = {'Authorization': f'Bearer {access_token}'}

    # Get user info
    user_resp = requests.get(f'{DISCORD_API_BASE}/users/@me', headers=user_headers)
    if user_resp.status_code != 200:
        return render_result(False, 'Failed to fetch your Discord profile.')

    user = user_resp.json()
    user_id = user['id']
    username = user.get('global_name') or user.get('username', 'Unknown')
    avatar_hash = user.get('avatar')
    avatar_url = f'https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128' if avatar_hash else 'https://cdn.discordapp.com/embed/avatars/0.png'

    # Get profile via bot token
    bot_headers = {'Authorization': f'Bot {BOT_TOKEN}'}
    profile_resp = requests.get(
        f'{DISCORD_API_BASE}/users/{user_id}/profile',
        headers=bot_headers,
        params={'guild_id': GUILD_ID}
    )

    bio = ''
    clan_tag = ''
    if profile_resp.status_code == 200:
        profile = profile_resp.json()
        bio = profile.get('user_profile', {}).get('bio') or ''
        clan = profile.get('clan') or {}
        clan_tag = clan.get('tag', '')

    bio_ok = REQUIRED_BIO.lower() in bio.lower()
    tag_ok = clan_tag.upper() == REQUIRED_TAG.upper()

    # Store in session for the confirm step
    session['user_id'] = user_id
    session['bio_ok'] = bio_ok
    session['tag_ok'] = tag_ok

    if not bio_ok or not tag_ok:
        issues = []
        if not bio_ok:
            issues.append(f'Your bio must contain <code>{REQUIRED_BIO}</code>')
        if not tag_ok:
            issues.append(f'You must have the <code>{REQUIRED_TAG}</code> clan tag equipped')
        return render_result(False,
            'Verification failed:<br><br>' +
            '<br>'.join(f'❌ {i}' for i in issues) +
            f'<br><br>Fix the above and <a href="/verify">try again</a>.'
        )

    # Show step 2 — confirm page
    return render_confirm(username, avatar_url)


@app.route('/confirm', methods=['POST'])
def confirm():
    """Step 2: User clicked the big button — assign the role"""
    user_id = session.get('user_id')
    bio_ok  = session.get('bio_ok')
    tag_ok  = session.get('tag_ok')

    if not user_id or not bio_ok or not tag_ok:
        return render_result(False, 'Session expired or invalid. <a href="/verify">Try again</a>.')

    resp = requests.post(BOT_API_URL, json={'user_id': user_id},
                         headers={'X-Internal-Secret': INTERNAL_SECRET})

    if resp.status_code == 200:
        session.clear()
        return render_result(True, "You've been verified! Head back to the server 🎉")
    else:
        return render_result(False, 'Something went wrong assigning your role. Try again later.')


def render_confirm(username: str, avatar_url: str):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify — Step 2</title>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #0e0f13;
      font-family: 'DM Sans', sans-serif;
      color: #fff;
    }}
    .card {{
      background: #16181f;
      border: 1px solid #2a2d38;
      border-radius: 16px;
      padding: 48px 40px;
      max-width: 460px;
      width: 90%;
      text-align: center;
      box-shadow: 0 0 60px rgba(0,0,0,0.4);
    }}
    .step {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #5865F2;
      font-weight: 600;
      margin-bottom: 20px;
    }}
    .avatar {{
      width: 80px;
      height: 80px;
      border-radius: 50%;
      border: 3px solid #5865F2;
      margin-bottom: 16px;
    }}
    h1 {{
      font-family: 'Syne', sans-serif;
      font-size: 1.5rem;
      color: #fff;
      margin-bottom: 8px;
    }}
    .username {{
      color: #5865F2;
      font-weight: 600;
    }}
    p {{
      color: #a0a3b1;
      line-height: 1.7;
      font-size: 0.95rem;
      margin-bottom: 32px;
      margin-top: 12px;
    }}
    .checks {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-bottom: 32px;
      text-align: left;
    }}
    .check-item {{
      background: #1e2029;
      border: 1px solid #2a2d38;
      border-radius: 10px;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 0.9rem;
      color: #c8cad4;
    }}
    .check-icon {{ font-size: 1.1rem; }}
    button {{
      width: 100%;
      padding: 16px;
      background: #5865F2;
      color: #fff;
      border: none;
      border-radius: 12px;
      font-family: 'Syne', sans-serif;
      font-size: 1.1rem;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
      letter-spacing: 0.02em;
    }}
    button:hover {{ background: #4752c4; transform: translateY(-1px); }}
    button:active {{ transform: translateY(0); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="step">Step 2 of 2</div>
    <img class="avatar" src="{avatar_url}" alt="avatar">
    <h1>Hey, <span class="username">{username}</span>!</h1>
    <p>Your profile checks out. Click the button below to get verified and access the server.</p>
    <div class="checks">
      <div class="check-item"><span class="check-icon">✅</span> Bio contains <strong style="color:#fff;margin-left:4px">{REQUIRED_BIO}</strong></div>
      <div class="check-item"><span class="check-icon">✅</span> Clan tag <strong style="color:#fff;margin-left:4px">{REQUIRED_TAG}</strong> is equipped</div>
    </div>
    <form method="POST" action="/confirm">
      <button type="submit">✅ &nbsp; Complete Verification</button>
    </form>
  </div>
</body>
</html>'''


def render_result(success: bool, message: str):
    color = '#57F287' if success else '#ED4245'
    icon  = '✅' if success else '❌'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verification</title>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #0e0f13;
      font-family: 'DM Sans', sans-serif;
      color: #fff;
    }}
    .card {{
      background: #16181f;
      border: 1px solid #2a2d38;
      border-radius: 16px;
      padding: 48px 40px;
      max-width: 460px;
      width: 90%;
      text-align: center;
      box-shadow: 0 0 60px rgba(0,0,0,0.4);
    }}
    .icon {{ font-size: 48px; margin-bottom: 16px; }}
    h1 {{
      font-family: 'Syne', sans-serif;
      font-size: 1.6rem;
      color: {color};
      margin-bottom: 16px;
    }}
    p {{ color: #a0a3b1; line-height: 1.7; font-size: 0.95rem; }}
    code {{
      background: #2a2d38;
      padding: 2px 6px;
      border-radius: 4px;
      color: #e2e3e8;
      font-size: 0.9em;
    }}
    a {{ color: {color}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{"Verified!" if success else "Verification Failed"}</h1>
    <p>{message}</p>
  </div>
</body>
</html>'''


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
