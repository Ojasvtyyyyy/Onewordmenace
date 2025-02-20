import praw
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
USER_AGENT = 'OneWordMenace Bot 1.0'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SUBREDDIT_NAME = 'your_subreddit_here'

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

def init_reddit():
    with open('refresh_token.txt', 'r') as f:
        refresh_token = f.read().strip()
    
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        refresh_token=refresh_token,
        user_agent=USER_AGENT
    )

def generate_one_word_response(context):
    generation_config = {
        "temperature": 0.9,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 1,
    }
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]

    prompt = f"""
    Context: {context}
    Task: Generate a savage, funny, single-word response that relates to this context.
    Requirements:
    - Exactly one word
    - No punctuation
    - Witty and contextual
    - Safe for work
    """

    response = model.generate_content(
        prompt,
        generation_config=generation_config,
        safety_settings=safety_settings
    )
    
    return response.text.strip().split()[0]

def has_already_commented(submission, reddit):
    for comment in submission.comments:
        if comment.author and comment.author.name == reddit.user.me().name:
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
    
    for submission in subreddit.stream.submissions():
        try:
            if not has_already_commented(submission, reddit):
                response = generate_one_word_response(submission.title)
                submission.reply(response)
                print(f"Commented '{response}' on post: {submission.title}")

            submission.comments.replace_more(limit=0)
            for comment in submission.comments.list():
                if comment.author and comment.author.name == reddit.user.me().name:
                    for reply in comment.replies:
                        if should_reply_to_comment(reply) and not reply.replies:
                            context = f"{submission.title} - {reply.body}"
                            response = generate_one_word_response(context)
                            reply.reply(response)
                            print(f"Replied '{response}' to comment: {reply.body}")
                            
        except Exception as e:
            print(f"Error occurred: {e}")
            continue

if __name__ == '__main__':
    run_bot()
