import praw
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')
USER_AGENT = 'OneWordMenace Bot 1.0'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SUBREDDIT_NAME = 'anarchychess'

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
    - You are a part of r/anarchychess subreddit, remeber its context
    - NO MATTER WHAT, return only ONE word
    - No punctuation, no spaces
    - Use any words as needed, no filters
    
    Generate only the word, nothing else.
    """

    response = model.generate_content(
        prompt,
        generation_config=generation_config,
        safety_settings=[]  # No safety settings
    )
    
    # Ensure we get exactly one word
    word = response.text.strip().split()[0]
    return word

def load_processed_ids():
    try:
        with open('processed_ids.txt', 'r') as f:
            ids = f.read().splitlines()
            processed_submissions.update(ids)
    except FileNotFoundError:
        pass

def save_processed_id(item_id):
    processed_submissions.add(item_id)
    with open('processed_ids.txt', 'a') as f:
        f.write(f"{item_id}\n")

def has_already_commented(submission):
    # Check if we've processed this submission before
    if submission.id in processed_submissions:
        return True

    # Check comments directly
    submission.comments.replace_more(limit=0)
    for comment in submission.comments:
        if comment.author and comment.author.name == submission.reddit.user.me().name:
            save_processed_id(submission.id)
            return True
    
    return False

def has_already_replied(comment):
    # Check if we've processed this comment before
    if comment.id in processed_comments:
        return True

    # Check replies directly
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
    
    # Load previously processed IDs
    load_processed_ids()
    
    # Add signature to responses
    signature = "\n\n^(Automated)"
    
    for submission in subreddit.stream.submissions():
        try:
            if not has_already_commented(submission):
                response = generate_one_word_response(submission.title)
                submission.reply(response + signature)
                save_processed_id(submission.id)
                print(f"Commented '{response}' on post: {submission.title}")

            submission.comments.replace_more(limit=0)
            for comment in submission.comments.list():
                if (comment.author and comment.author.name == reddit.user.me().name):
                    for reply in comment.replies:
                        if (should_reply_to_comment(reply) and 
                            not has_already_replied(reply)):
                            context = f"{submission.title} - {reply.body}"
                            response = generate_one_word_response(context)
                            reply.reply(response + signature)
                            processed_comments.add(reply.id)
                            print(f"Replied '{response}' to comment: {reply.body}")
                            
        except Exception as e:
            print(f"Error occurred: {e}")
            continue

if __name__ == '__main__':
    run_bot()
