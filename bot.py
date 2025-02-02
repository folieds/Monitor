import subprocess
import sys

# Ensure required pip packages are installed
required_packages = ['pyTelegramBotAPI', 'requests', 'beautifulsoup4', 'flask']
for package in required_packages:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

import os
import json
import telebot
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7655800312:AAEa0KIzkCAclMZyI3pBRLXkpOHily6rtnI")
CHAT_ID = os.getenv("CHAT_ID", "6314066171")
MONITOR_FILE = "monitored_accounts.json"

# List of approved user IDs
APPROVED_USERS = [6314066171, 12]  # Replace with actual user IDs
ADMIN_IDS = [6314066171]  # Replace with your admin user ID

def is_user_approved(user_id):
    """Check if the user is in the approved list."""
    return user_id in APPROVED_USERS

# Initialize Flask for keep-alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive"

def run_flask():
    app.run(host='0.0.0.0', port=8090)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# Initialize Telegram Bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

monitored_accounts = {}  # Example structure: {user_id: {username: account_details}}

# Load monitored accounts from file
def load_monitored_accounts():
    try:
        with open(MONITOR_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save monitored accounts to file
def save_monitored_accounts():
    with open(MONITOR_FILE, "w") as f:
        json.dump(monitored_accounts, f)

# Initialize monitored accounts
monitored_accounts = load_monitored_accounts()

APPROVED_USERS_FILE = "approved_users.json"  # File to save approved users

def load_approved_users():
    try:
        with open(APPROVED_USERS_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}

try:
    APPROVED_USERS = load_approved_users()  # Ensure this function returns a dictionary
except Exception:
    APPROVED_USERS = {}  # Fallback to an empty dictionary

def save_approved_users():
    with open(APPROVED_USERS_FILE, "w") as f:
        json.dump(APPROVED_USERS, f)
        
def is_user_approved(user_id):
    """Check if the user is in the approved list."""
    return str(user_id) in APPROVED_USERS

def schedule_unapprove(user_id, expiration_time):
    """Automatically unapprove a user after their approval expires."""
    time_to_wait = (expiration_time - datetime.now()).total_seconds()
    if time_to_wait > 0:
        import time
        time.sleep(time_to_wait)  # Wait until the expiration time

    if str(user_id) in APPROVED_USERS:
        APPROVED_USERS.pop(str(user_id))
        save_approved_users()
        print(f"User {user_id} has been automatically unapproved.")

def reapprove_users():
    """Reapprove users from file on startup."""
    current_time = datetime.now()
    users_to_remove = []  # Collect expired users for removal

    for user_id, expiry_str in APPROVED_USERS.items():
        expiration_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        if expiration_time <= current_time:
            # User has already expired
            print(f"User {user_id}'s approval has expired. Removing...")
            users_to_remove.append(user_id)
        else:
            # User is still approved; calculate remaining time
            remaining_time = (expiration_time - current_time).total_seconds()
            print(f"Reapproving user {user_id} for {remaining_time} seconds.")
            Thread(target=schedule_unapprove, args=(user_id, expiration_time)).start()

    # Remove expired users from APPROVED_USERS
    for user_id in users_to_remove:
        APPROVED_USERS.pop(user_id)

    save_approved_users()  # Save updated list
    
def is_user_approved(user_id):
    """Check if the user is approved and their approval hasn't expired."""
    user_id = str(user_id)
    if user_id in APPROVED_USERS:
        expiration_time = datetime.strptime(APPROVED_USERS[user_id], "%Y-%m-%d %H:%M:%S")
        if expiration_time > datetime.now():
            return True  # User is approved and their time hasn't expired
        else:
            # Remove expired user
            APPROVED_USERS.pop(user_id)
            save_approved_users()
            print(f"User {user_id}'s approval has expired and they have been removed.")
    return False

def check_instagram_status(username):
    """Check if an Instagram account exists."""
    url = f"https://www.instagram.com/{username}/"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            account_exists = soup.find('meta', property='og:description')
            print(f"Account @{username} exists: {bool(account_exists)}")
            return bool(account_exists)
        elif response.status_code == 404:
            print(f"Account @{username} is banned or does not exist.")
            return False
        else:
            print(f"Unexpected status code {response.status_code} for @{username}")
            return None
    except requests.RequestException as e:
        print(f"HTTP request failed for @{username}: {e}")
        return None

def custom_escape_markdown(text):
    """Escape special characters for Telegram MarkdownV2."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return ''.join(f"\\{char}" if char in escape_chars else char for char in text)

def monitor_account(username):
    """Monitor account status periodically."""
    while username in monitored_accounts:
        status = check_instagram_status(username)
        
        account_data = monitored_accounts.get(username)
        if account_data and isinstance(account_data, dict):
            if account_data.get('exists') and not status:
                notify_status_change(username, "banned")
                monitored_accounts.pop(username)
                save_monitored_accounts()
                break
            elif not account_data['exists'] and status:
                notify_status_change(username, "unbanned")
                monitored_accounts.pop(username)
                save_monitored_accounts()
                break
        
        # Wait before checking again
        telebot.time.sleep(20)  # Set interval to 20 seconds

def notify_status_change(username, status):
    """Send a status change notification with time taken."""
    start_time = datetime.strptime(monitored_accounts[username]['start_time'], "%Y-%m-%d %H:%M:%S")
    end_time = datetime.now()
    user_id = monitored_accounts[username]['user_id']  # Get the user ID who started monitoring

    # Calculate time difference
    time_diff = end_time - start_time
    days = time_diff.days
    seconds = time_diff.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    # Format the time message
    time_message = ""
    if days > 0:
        time_message += f"{days} day{'s' if days > 1 else ''} "
    if hours > 0 or days > 0:
        time_message += f"{hours} hour{'s' if hours > 1 else ''} "
    if minutes > 0 or hours > 0 or days > 0:
        time_message += f"{minutes} minute{'s' if minutes > 1 else ''} "
    time_message += f"{seconds} second{'s' if seconds != 1 else ''}"

    # Determine the appropriate status message
    if status == "unbanned":
        message = f"@{username} is Recovered! Took {time_message}"
    elif status == "banned":
        message = f"@{username} is Smoked! Took {time_message}"
    
    # Send the notification only to the user who initiated the monitoring
    bot.send_message(user_id, message, parse_mode='Markdown')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with commands."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this bot.")
        return

    help_text = """🤖 Instagram Monitoring Bot Commands:

/unban <username> - Monitor an account for unbanning
/ban <username> - Monitor an account for banning
/status <username> - Check the current status of an account
/stop <username> - Stop monitoring an account
/monitorlist - List all monitored accounts
/approve <user_id> - Approve a user to use the bot (Admin only)
/unapprove <user_id> - Unapprove a user to restrict access (Admin only)"""
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['approve'])
def approve_user(message):
    """Approve a user to use the bot for a specific duration."""
    global APPROVED_USERS  # Explicitly refer to the global APPROVED_USERS variable

    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    try:
        args = message.text.split(' ')
        user_id = int(args[1])
        duration = " ".join(args[2:])

        # Parse duration into days, hours, and seconds
        days, hours, seconds = 0, 0, 0
        for part in duration.split():
            if part.endswith('d'):
                days += int(part[:-1])
            elif part.endswith('h'):
                hours += int(part[:-1])
            elif part.endswith('s'):
                seconds += int(part[:-1])

        expiration_time = datetime.now() + timedelta(days=days, hours=hours, seconds=seconds)

        # Ensure APPROVED_USERS is a dictionary
        if not isinstance(APPROVED_USERS, dict):
            APPROVED_USERS = {}

        APPROVED_USERS[str(user_id)] = expiration_time.strftime("%Y-%m-%d %H:%M:%S")
        save_approved_users()

        bot.reply_to(
            message,
            f"✅ Successfully approved user {user_id} for {days} days {hours} hours {seconds} seconds."
        )

        # Schedule automatic removal after the specified time
        Thread(target=schedule_unapprove, args=(user_id, expiration_time)).start()

    except (IndexError, ValueError):
        bot.reply_to(message, "❗ Please provide a valid user ID and duration. Usage: /approve <user_id> <duration>")

@bot.message_handler(commands=['unapprove'])
def unapprove_user(message):
    """Unapprove a user to restrict them from using the bot."""
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 Only admins can unapprove users.")
        return

    try:
        user_id = int(message.text.split(' ')[1])
        if user_id in APPROVED_USERS:
            APPROVED_USERS.remove(user_id)
            bot.reply_to(message, f"🚫 User {user_id} has been unapproved.")
        else:
            bot.reply_to(message, f"ℹ️ User {user_id} is not in the approved list.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❗ Please provide a valid user ID. Usage: /unapprove <user_id>")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with commands."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this bot.")
        return

    help_text = """🤖 Instagram Monitoring Bot Commands:

/unban <username> - Monitor an account for unbanning
/ban <username> - Monitor an account for banning
/status <username> - Check the current status of an account
/stop <username> - Stop monitoring an account
/monitorlist - List all monitored accounts
/approve <user_id> - Approve a user to use the bot (Admin only)
/unapprove <user_id> - Unapprove a user to restrict access (Admin only)"""
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['status'])
def check_status(message):
    """Check the current status of an account."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    try:
        username = message.text.split(' ')[1]
    except IndexError:
        bot.reply_to(message, "❗ Please provide a username. Usage: /status <username>")
        return

    status = check_instagram_status(username)
    if status is None:
        bot.reply_to(message, f"❗ Unable to check the status of @{username}. Please try again later.")
    elif status:
        bot.reply_to(message, f"✅ @{username} is currently Active.")
    else:
        bot.reply_to(message, f"🚨 @{username} is currently Banned.")

@bot.message_handler(commands=['unban'])
def watch_unban(message):
    """Monitor an account for unbanning."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    try:
        username = message.text.split(' ')[1]
    except IndexError:
        bot.reply_to(message, "❗ Please provide a username. Usage: /unban <username>")
        return

    if username in monitored_accounts:
        bot.reply_to(message, f"@{username} is already being monitored.")
        return

    exists = check_instagram_status(username)
    if exists is None:
        bot.reply_to(message, f"❗ Unable to check the status of @{username}. Try again later.")
        return

    if exists:
        bot.reply_to(message, f"ℹ️ @{username} is active. No need to monitor for unban.")
    else:
        bot.reply_to(message, f"🚨 @{username} is banned. Monitoring started for unban.")
        monitored_accounts[username] = {
            'exists': False,
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'type': 'unban',
            'user_id': message.from_user.id  # Store the user ID
        }
        save_monitored_accounts()
        Thread(target=monitor_account, args=(username,)).start()

@bot.message_handler(commands=['ban'])
def watch_ban(message):
    """Monitor an account for banning."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    try:
        username = message.text.split(' ')[1]
    except IndexError:
        bot.reply_to(message, "❗ Please provide a username. Usage: /ban <username>")
        return

    if username in monitored_accounts:
        bot.reply_to(message, f"@{username} is already being monitored.")
        return

    exists = check_instagram_status(username)
    if exists is None:
        bot.reply_to(message, f"❗ Unable to check the status of @{username}. Try again later.")
        return

    if not exists:
        bot.reply_to(message, f"@{username} is already banned. No need to monitor for ban.")
    else:
        bot.reply_to(message, f"🚨 @{username} is active. Monitoring started for ban.")
        monitored_accounts[username] = {
            'exists': True,
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'type': 'ban',
            'user_id': message.from_user.id  # Store the user ID
        }
        save_monitored_accounts()
        Thread(target=monitor_account, args=(username,)).start()

@bot.message_handler(commands=['stop'])
def stop(message):
    """Stop monitoring an Instagram account."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    try:
        username = message.text.split(' ')[1]
    except IndexError:
        bot.reply_to(message, "❗ Please provide a username. Usage: /stop <username>")
        return
    
    if username in monitored_accounts:
        monitored_accounts.pop(username)
        save_monitored_accounts()
        bot.reply_to(message, f"🛑 Stopped monitoring @{username}.")
    else:
        bot.reply_to(message, f"@{username} is not being monitored.")

@bot.message_handler(commands=['monitorlist'])
def monitor_list(message):
    """List all monitored accounts."""
    if not is_user_approved(message.from_user.id):
        bot.reply_to(message, "🚫 You are not authorized to use this command.")
        return

    if not monitored_accounts:
        bot.reply_to(message, "ℹ️ No accounts are currently being monitored.")
        return

    response = "📄 *Monitored Accounts:*\n\n"
    
    for username, details in monitored_accounts.items():
        if isinstance(details, dict):
            status = "Unban" if details.get('type') == 'unban' else "Ban"
            escaped_username = custom_escape_markdown(username)
            response += f"`{escaped_username}`: Monitoring for *{status}*\n"
    
    try:
        bot.reply_to(message, response, parse_mode='MarkdownV2')
    except Exception as e:
        print(f"Error sending monitor list: {e}")

# Start the bot
keep_alive()

# Re-start monitoring for previously monitored accounts
for username, details in monitored_accounts.items():
    if details.get('exists') is not None:  # If the account was being monitored
        Thread(target=monitor_account, args=(username,)).start()

from flask import Flask, request, jsonify
from threading import Thread

# Define the Flask app
app = Flask(__name__)

@app.route('/dashboard/<int:user_id>', methods=['GET'])
def user_dashboard(user_id):
    """Serve the dashboard for a specific user."""
    user_id = str(user_id)
    if user_id not in monitored_accounts:
        return jsonify({"message": "No monitored accounts found."})

    return jsonify(monitored_accounts[user_id])

def run_flask():
    app.run(host='0.0.0.0', port=5000)  # Expose Flask on port 5000

# Run both the bot and Flask server
Thread(target=run_flask).start()
bot.polling(none_stop=True)

bot.polling(none_stop=True)
