from flask import Flask, request, os
import requests

app = Flask(__name__)

CLIENT_ID       = os.environ['CLIENT_ID']
CLIENT_SECRET   = os.environ['CLIENT_SECRET']
REDIRECT_URI    = os.environ['REDIRECT_URI']
INTERNAL_SECRET = os.environ['INTERNAL_SECRET']
BOT_API_URL     = 'http://localhost:8081/internal/oauth-callback'

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "<h1>Error</h1><p>No code received.</p>", 400

    # Exchange code for access token
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    r = requests.post('https://discord.com/api/v10/oauth2/token', data=data)
    if r.status_code != 200:
        return f"<h1>Auth Failed</h1><p>{r.text}</p>", 400

    token = r.json().get('access_token')
    
    # Get User ID
    u = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {token}'})
    user_id = u.json().get('id')

    # Notify Bot via internal API
    try:
        requests.post(BOT_API_URL, json={'user_id': user_id}, headers={'X-Internal-Secret': INTERNAL_SECRET}, timeout=5)
    except Exception as e:
        print(f"Error notifying bot: {e}")

    # Professional response that closes the tab automatically
    return """
    <html>
        <body style="background:#0e0f13;color:white;text-align:center;font-family:sans-serif;padding-top:100px;">
            <h1 style="color:#57F287;font-size:40px;">✅ Authorized!</h1>
            <p style="font-size:20px;color:#a0a3b1;">This window will close automatically in 3 seconds.</p>
            <p>Go back to Discord and click <b>Verify Me</b>.</p>
            <script>
                setTimeout(function(){ window.close(); }, 3000);
            </script>
        </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
