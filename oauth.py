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
    return '''
    <h1>Bot OAuth Service</h1>
    <p>Click below to authorize the bot:</p>
    <a href="/authorize"><button>Authorize Bot</button></a>
    '''

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
    
    authorization_url = reddit.auth.url(['identity', 'submit', 'read', 'history'], state, 'permanent')
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    error = request.args.get('error')
    if error:
        return f'Error during authorization: {error}'

    state = request.args.get('state')
    code = request.args.get('code')
    
    if not state or not code:
        return 'Missing state or code. Authorization failed.'
    
    if state != session.get('state'):
        return 'State mismatch. Authorization failed.'

    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            user_agent=USER_AGENT
        )
        
        refresh_token = reddit.auth.authorize(code)
        
        return f'''
        <h2>Authorization Successful!</h2>
        <p>Your refresh token is:</p>
        <pre>{refresh_token}</pre>
        <p>Important: Save this token and add it to your environment variables as REFRESH_TOKEN</p>
        <p style="color: red;">This token will only be shown once!</p>
        '''
        
    except Exception as e:
        return f'Error during token generation: {str(e)}'

@app.route('/test_token')
def test_token():
    refresh_token = request.args.get('token')
    if not refresh_token:
        return 'Please provide a token as ?token=your_token'
    
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            refresh_token=refresh_token,
            user_agent=USER_AGENT
        )
        username = reddit.user.me().name
        return f'Success! Authenticated as: {username}'
    except Exception as e:
        return f'Token test failed: {str(e)}'

if __name__ == '__main__':
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDIRECT_URI]):
        print("Error: Missing environment variables. Please check your .env file.")
        print("Required variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDIRECT_URI")
        exit(1)
        
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
