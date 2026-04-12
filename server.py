from flask import Flask, redirect, request
import requests
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ============================================================
#  All secrets loaded from environment variables — safe for public GitHub
# ============================================================
CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']
REQUIRED_BIO    = os.environ.get('REQUIRED_BIO', 'discord.gg/justjoin')
REQUIRED_TAG    = os.environ.get('REQUIRED_TAG', 'BACK')
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
BOT_API_URL     = 'http://localhost:8081/internal/assign-role'
# ============================================================

DISCORD_AUTH_URL  = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_API_BASE  = 'https://discord.com/api/v10'
SCOPES = 'identify'


@app.route('/verify')
def verify():
    params = (
        f'client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&response_type=code'
        f'&scope={SCOPES}'
    )
    return redirect(f'{DISCORD_AUTH_URL}?{params}')


@app.route('/callback')
def callback():
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
    headers = {'Authorization': f'Bearer {access_token}'}

    # Get user ID
    user_resp = requests.get(f'{DISCORD_API_BASE}/users/@me', headers=headers)
    if user_resp.status_code != 200:
        return render_result(False, 'Failed to fetch your Discord profile.')
    user_id = user_resp.json()['id']

    # Get real profile (bio + clan tag) — works with user OAuth token
    profile_resp = requests.get(f'{DISCORD_API_BASE}/users/@me/profile', headers=headers)
    bio = ''
    clan_tag = ''
    if profile_resp.status_code == 200:
        profile = profile_resp.json()
        bio = profile.get('user_profile', {}).get('bio') or ''
        clan = profile.get('clan') or {}
        clan_tag = clan.get('tag', '')

    bio_ok = REQUIRED_BIO.lower() in bio.lower()
    tag_ok = clan_tag.upper() == REQUIRED_TAG.upper()

    if bio_ok and tag_ok:
        requests.post(BOT_API_URL, json={'user_id': user_id},
                      headers={'X-Internal-Secret': INTERNAL_SECRET})
        return render_result(True, "You've been verified! Head back to the server 🎉")

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
    app.run(host='0.0.0.0', port=8080)
