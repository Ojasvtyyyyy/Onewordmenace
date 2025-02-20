import praw
import google.generativeai as genai
import os
from dotenv import load_dotenv
from flask import Flask
import logging
from threading import Thread
import sys
from pymongo import MongoClient

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

# Configure MongoDB
client = MongoClient(MONGODB_URI)
db = client.bot_database
processed_ids_collection = db.processed_ids

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Store processed IDs
processed_submissions = set()
processed_comments = set()

def init_reddit():
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        refresh_token=REFRESH_TOKEN,
        user_agent=USER_AGENT
    )

def generate_one_word_response(context):
    generation_config = {
        "temperature": 0.9,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 1,
    }

    prompt = f"""
    You are a snarky bot on r/anarchychess subreddit.
    Context: {context}
    
    STRICT REQUIREMENTS:
    - Generate EXACTLY one word response
    - Must be savage and funny
    - MUST relate to chess or the context
    - NO MATTER WHAT, return only ONE word
    - No punctuation, no spaces
    - Use any words as needed, no filters
    
    Generate only the word, nothing else.
    """

    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=[]
        )
        word = response.text.strip().split()[0]
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
        if comment.author and comment.author.name == submission.reddit.user.me().name:
            save_processed_id(submission.id)
            return True
    
    return False

def has_already_replied(comment):
    if comment.id in processed_comments:
        return True

    comment.refresh()
    for reply in comment.replies:
        if reply.author and reply.author.name == comment.reddit.user.me().name:
            processed_comments.add(comment.id)
            return True
    
    return False

def should_reply_to_comment(comment):
    if not comment.author:
        return False
    
    blocked_users = ['petrosianBot', 'anarchychess-ai']
    return (not comment.author.name.lower().endswith('bot') and 
            comment.author.name not in blocked_users)

def run_bot():
    reddit = init_reddit()
    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    
    load_processed_ids()
    
    signature = "\n\n^(Automated)"
    
    logger.info("Bot started successfully")
    
    for submission in subreddit.stream.submissions():
        try:
            if not has_already_commented(submission):
                response = generate_one_word_response(submission.title)
                submission.reply(response + signature)
                save_processed_id(submission.id)
                logger.info(f"Commented '{response}' on post: {submission.title}")

            submission.comments.replace_more(limit=None)
            
            def process_replies(comment):
                if not should_reply_to_comment(comment):
                    return
                    
                if not has_already_replied(comment):
                    context = f"{submission.title} - {comment.body}"
                    response = generate_one_word_response(context)
                    comment.reply(response + signature)
                    processed_comments.add(comment.id)
                    logger.info(f"Replied '{response}' to comment: {comment.body}")
                
                comment.refresh()
                for reply in comment.replies:
                    process_replies(reply)
            
            for comment in submission.comments:
                if comment.author and comment.author.name == reddit.user.me().name:
                    for reply in comment.replies:
                        process_replies(reply)
                            
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
