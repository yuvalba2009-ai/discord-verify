from flask import Flask, request, render_template_string
import requests
import os

app = Flask(__name__)

CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
BOT_API_URL     = 'http://localhost:8081/internal/oauth-callback'

DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_API_BASE  = 'https://discord.com/api/v10'

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return render_result(False, 'No authorization code received.')

    token_resp = requests.post(DISCORD_TOKEN_URL, data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'})

    if token_resp.status_code != 200:
        return render_result(False, 'Failed to get access token.')

    access_token = token_resp.json()['access_token']
    user_resp = requests.get(f'{DISCORD_API_BASE}/users/@me',
                             headers={'Authorization': f'Bearer {access_token}'})
    
    if user_resp.status_code != 200:
        return render_result(False, 'Failed to fetch profile.')

    user_id = user_resp.json()['id']
    
    # Notify the bot
    requests.post(BOT_API_URL, json={'user_id': user_id},
                  headers={'X-Internal-Secret': INTERNAL_SECRET})

    return render_result(True, 'Authorization complete! Go back to Discord and click Verify Me.')

def render_result(success: bool, message: str):
    color = '#57F287' if success else '#ED4245'
    return f"<html><body style='background:#0e0f13;color:white;text-align:center;font-family:sans-serif;'><h1 style='color:{color}'>{message}</h1></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
