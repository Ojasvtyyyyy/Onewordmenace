from flask import Flask, redirect, request, session
import praw
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
USER_AGENT = 'OneWordMenace Bot 1.0'

@app.route('/')
def home():
    return 'Bot OAuth Service Running'

@app.route('/authorize')
def authorize():
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        user_agent=USER_AGENT
    )
    
    state = os.urandom(16).hex()
    session['state'] = state
    
    authorization_url = reddit.auth.url(['identity', 'submit', 'read'], state, 'permanent')
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    state = request.args.get('state')
    code = request.args.get('code')
    
    if state != session.get('state'):
        return 'State mismatch. Authorization failed.'

    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        user_agent=USER_AGENT
    )
    
    refresh_token = reddit.auth.authorize(code)
    
    # Store the refresh token securely
    with open('refresh_token.txt', 'w') as f:
        f.write(refresh_token)
    
    return 'Authorization successful! You can close this window.'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
