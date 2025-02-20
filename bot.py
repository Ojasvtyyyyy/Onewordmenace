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
processed_collection = db.processed_items

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
processed_items = set()
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

def generate_one_word_response(text, context=None):
    try:
        generation_config = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8,
            "stop_sequences": ["\n", ".", " "]
        }

        content = f"Content: {text}"
        if context:
            content += f"\nContext: {context}"

        prompt = f"""You are a mischievous sarcastic bot on Reddit.

{content}

Task: Generate a single savage, snarky word response.
Requirements:
- Must be EXACTLY one word
- Be extremely creative and snarky
- Can be ANY word - no topic restrictions
- Make it witty and relevant to the content
- No spaces or punctuation
- Can be slang, strong language, or regular words
- The snarkier and more clever, the better

Generate the single word response now:"""

        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )

        word = response.text.strip().split()[0].lower()
        word = ''.join(c for c in word if c.isalnum())
        
        if not word or len(word) > 20:
            return "bruh"
            
        return word

    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return "bruh"

def load_processed_ids():
    try:
        for doc in processed_collection.find():
            processed_items.add(doc['item_id'])
        logger.info(f"Loaded {len(processed_items)} processed IDs")
    except Exception as e:
        logger.error(f"Error loading processed IDs: {e}")

def save_processed_id(item_id, item_type):
    try:
        processed_items.add(item_id)
        processed_collection.update_one(
            {'item_id': item_id},
            {'$set': {
                'item_id': item_id,
                'type': item_type,
                'processed_at': datetime.utcnow()
            }},
            upsert=True
        )
        logger.info(f"Saved new {item_type} ID: {item_id}")
    except Exception as e:
        logger.error(f"Error saving processed ID: {e}")

def is_processed(item_id):
    return item_id in processed_items

def should_process_user(username):
    if not username:
        return False
    
    blocked_users = ['AutoModerator', 'petrosianBot', 'anarchychess-ai']
    return (not username.lower().endswith('bot') and 
            username not in blocked_users)

def safe_reddit_action(action_func):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return action_func()
        except PrawcoreException as e:
            if 'RATELIMIT' in str(e):
                wait_time = int(str(e).split('break for ')[1].split(' ')[0])
                logger.info(f"Rate limited. Waiting {wait_time} minutes...")
                time.sleep(wait_time * 60 + 10)
                continue
            else:
                raise
    return None

def process_submission(submission):
    if not is_processed(submission.id) and should_process_user(submission.author.name):
        response = generate_one_word_response(submission.title)
        
        def post_comment():
            submission.reply(response + "\n\n^(Automated)")
        
        safe_reddit_action(post_comment)
        save_processed_id(submission.id, 'submission')
        logger.info(f"Commented '{response}' on post: {submission.title}")

def process_comment(comment):
    if not is_processed(comment.id) and should_process_user(comment.author.name):
        # Get parent content for context
        parent_content = None
        try:
            if comment.parent_id.startswith('t1_'):  # parent is a comment
                parent = reddit.comment(comment.parent_id[3:])
                parent_content = parent.body
            elif comment.parent_id.startswith('t3_'):  # parent is a submission
                parent = reddit.submission(comment.parent_id[3:])
                parent_content = parent.title
        except:
            pass

        response = generate_one_word_response(comment.body, parent_content)
        
        def post_reply():
            comment.reply(response + "\n\n^(Automated)")
        
        safe_reddit_action(post_reply)
        save_processed_id(comment.id, 'comment')
        logger.info(f"Replied '{response}' to comment: {comment.body[:50]}...")

def run_bot():
    global reddit, bot_start_time
    reddit = init_reddit()
    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    bot_start_time = datetime.utcnow()
    
    load_processed_ids()
    
    logger.info("Bot started successfully")
    
    while True:
        try:
            # Process new submissions
            for submission in subreddit.stream.submissions():
                if submission.created_utc < bot_start_time.timestamp():
                    continue
                process_submission(submission)
            
            # Process new comments
            for comment in subreddit.stream.comments():
                if comment.created_utc < bot_start_time.timestamp():
                    continue
                process_comment(comment)
                
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(30)
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
