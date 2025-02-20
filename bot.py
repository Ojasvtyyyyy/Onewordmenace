import praw
import google.generativeai as genai
import os
from dotenv import load_dotenv
from flask import Flask
import logging
from threading import Thread
import sys
from pymongo import MongoClient
from prawcore.exceptions import PrawcoreException
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)

load_dotenv()

# Configuration
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')
USER_AGENT = 'OneWordMenace Bot 1.0'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SUBREDDIT_NAME = 'anarchychess'
PORT = int(os.getenv('PORT', 10000))
MONGODB_URI = os.getenv('MONGODB_URI')

# Validate API keys at startup
if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REFRESH_TOKEN, GEMINI_API_KEY, MONGODB_URI]):
    logger.error("Missing required environment variables!")
    sys.exit(1)

# Configure MongoDB
client = MongoClient(MONGODB_URI)
db = client.bot_database
processed_ids_collection = db.processed_ids

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Set safety settings to none for all categories
safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
]

# Initialize model with correct name and safety settings
model = genai.GenerativeModel(
    model_name='gemini-pro',
    safety_settings=safety_settings
)

# Store processed IDs and global reddit instance
processed_submissions = set()
processed_comments = set()
reddit = None
bot_start_time = None

def init_reddit():
    global reddit
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        refresh_token=REFRESH_TOKEN,
        user_agent=USER_AGENT
    )
    return reddit

def generate_one_word_response(post_title):
    try:
        # Configuration for precise one-word output
        generation_config = {
            "temperature": 1.0,  # Higher for more creative responses
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8,  # Allow slightly more for filtering
            "stop_sequences": ["\n", ".", " "]
        }

        chess_terms = [
            "pipi", "horsey", "en", "passant", "bongcloud", "mate", "rook", "bishop",
            "pawn", "queen", "king", "chess", "fork", "pin", "skewer", "zugzwang",
            "blunder", "brilliancy", "checkmate", "draw", "stalemate", "brick"
        ]

        prompt = f"""You are a mischievous sarcastic bot in r/anarchychess.
Post Title: {post_title}

Task: Generate a single savage, snarky word related to chess or the post.
Preferred words: {', '.join(chess_terms)}

Requirements:
- Must be EXACTLY one word
- Be creative but chess-related
- The snarkier the better
- No spaces or punctuation
- Must match the tone of r/anarchychess

Generate the single word response now:"""

        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )

        # Clean and validate response
        word = response.text.strip().split()[0].lower()
        
        # Remove any punctuation
        word = ''.join(c for c in word if c.isalnum())
        
        # Fallback if word is empty or too long
        if not word or len(word) > 20:
            return "pipi"
            
        return word

    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return "pipi"

def load_processed_ids():
    try:
        for doc in processed_ids_collection.find({}, {'submission_id': 1}):
            processed_submissions.add(doc['submission_id'])
        logger.info(f"Loaded {len(processed_submissions)} processed IDs")
    except Exception as e:
        logger.error(f"Error loading processed IDs: {e}")

def save_processed_id(item_id):
    try:
        processed_submissions.add(item_id)
        processed_ids_collection.update_one(
            {'submission_id': item_id},
            {'$set': {'submission_id': item_id}},
            upsert=True
        )
        logger.info(f"Saved new ID: {item_id}")
    except Exception as e:
        logger.error(f"Error saving processed ID: {e}")

def has_already_commented(submission):
    if submission.id in processed_submissions:
        return True

    submission.comments.replace_more(limit=0)
    for comment in submission.comments:
        if comment.author and comment.author.name == reddit.user.me().name:
            save_processed_id(submission.id)
            return True
    
    return False

def should_reply_to_comment(comment):
    if not comment.author:
        return False
    
    blocked_users = ['petrosianBot', 'anarchychess-ai']
    return (not comment.author.name.lower().endswith('bot') and 
            comment.author.name not in blocked_users)

def safe_reddit_action(action_func):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return action_func()
        except PrawcoreException as e:
            if 'RATELIMIT' in str(e):
                wait_time = int(str(e).split('break for ')[1].split(' ')[0])
                logger.info(f"Rate limited. Waiting {wait_time} minutes...")
                time.sleep(wait_time * 60 + 10)  # Add 10 seconds buffer
                continue
            else:
                raise
    return None

def run_bot():
    global reddit, bot_start_time
    reddit = init_reddit()
    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    bot_start_time = datetime.utcnow()
    
    load_processed_ids()
    
    signature = "\n\n^(Automated)"
    
    logger.info("Bot started successfully")
    
    for submission in subreddit.stream.submissions():
        try:
            # Only process submissions created after bot start
            if submission.created_utc < bot_start_time.timestamp():
                continue
                
            if not has_already_commented(submission):
                response = generate_one_word_response(submission.title)
                
                def post_comment():
                    submission.reply(response + signature)
                
                safe_reddit_action(post_comment)
                save_processed_id(submission.id)
                logger.info(f"Commented '{response}' on post: {submission.title}")
                
        except Exception as e:
            logger.error(f"Error processing submission: {e}")
            continue

@app.route('/health')
def health_check():
    return {'status': 'healthy', 'message': 'Bot is running'}, 200

@app.route('/')
def home():
    return {'status': 'online', 'message': 'OneWordMenace Bot'}, 200

def start_bot():
    thread = Thread(target=run_bot)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    start_bot()
    app.run(host='0.0.0.0', port=PORT)
