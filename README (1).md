# Discord Verify Bot

Verifies Discord members by checking their real bio and clan tag via OAuth2.

## Environment Variables

Set these in Railway (never put them in the code):

| Variable | Value |
|----------|-------|
| `DISCORD_TOKEN` | Your bot token |
| `GUILD_ID` | Your server ID |
| `ROLE_ID` | Role to assign |
| `CLIENT_ID` | OAuth2 client ID |
| `CLIENT_SECRET` | OAuth2 client secret |
| `REDIRECT_URI` | `https://YOUR_DOMAIN/callback` |
| `VERIFY_URL` | `https://YOUR_DOMAIN/verify` |
| `INTERNAL_SECRET` | Any random string (make one up) |
| `REQUIRED_BIO` | `discord.gg/justjoin` |
| `REQUIRED_TAG` | `BACK` |

## Start Command (Railway)
```
python server.py & python bot.py
```
