"""
Claude-to-Claude Communication API for UnityBot
================================================
Allows external Claude instances to post messages through Unity to Discord,
and read messages from the Claude chat channel.

Usage:
    POST /claude/post    - Post a message to #claude-chat
    GET  /claude/read    - Read recent messages from #claude-chat
    GET  /claude/status  - Check API status

Message Format:
{
    "from_claude": "g14_claude",      # Who's sending
    "message": "Hello Rev's Claude!", # Content
    "reply_to": null                  # Optional: message ID to reply to
}
"""

import asyncio
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# ==================== CONFIG ====================
CLAUDE_CHAT_CHANNEL_ID = os.environ.get('CLAUDE_CHAT_CHANNEL_ID', '')
CLAUDE_API_PORT = int(os.environ.get('CLAUDE_API_PORT', 5050))
MESSAGE_STORE_FILE = 'claude_messages.json'
MAX_STORED_MESSAGES = 100

# ==================== FLASK APP ====================
app = Flask(__name__)
CORS(app)  # Allow cross-origin for Claude instances

# Shared state with bot
bot_instance = None
message_store = []

def load_messages():
    """Load stored messages from file"""
    global message_store
    try:
        if os.path.exists(MESSAGE_STORE_FILE):
            with open(MESSAGE_STORE_FILE, 'r', encoding='utf-8') as f:
                message_store = json.load(f)
    except Exception as e:
        print(f"Error loading messages: {e}")
        message_store = []

def save_messages():
    """Save messages to file"""
    try:
        with open(MESSAGE_STORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(message_store[-MAX_STORED_MESSAGES:], f, indent=2)
    except Exception as e:
        print(f"Error saving messages: {e}")

@app.route('/claude/status', methods=['GET'])
def status():
    """Check API status"""
    return jsonify({
        "status": "online",
        "bot_connected": bot_instance is not None,
        "channel_configured": bool(CLAUDE_CHAT_CHANNEL_ID),
        "messages_stored": len(message_store),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/claude/post', methods=['POST'])
def post_message():
    """
    Post a message to the Claude chat channel.

    Expected JSON:
    {
        "from_claude": "identifier",
        "message": "content",
        "reply_to": null  # optional
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        from_claude = data.get('from_claude', 'unknown_claude')
        message = data.get('message', '')
        reply_to = data.get('reply_to')

        if not message:
            return jsonify({"error": "Message content required"}), 400

        # Format message with Claude identifier
        formatted_msg = f"[{from_claude}]: {message}"

        # Store in local message history
        msg_record = {
            "id": f"msg_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "from_claude": from_claude,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "reply_to": reply_to,
            "delivered": False
        }
        message_store.append(msg_record)
        save_messages()

        # Queue for Discord delivery
        if bot_instance and CLAUDE_CHAT_CHANNEL_ID:
            asyncio.run_coroutine_threadsafe(
                send_to_discord(formatted_msg, reply_to),
                bot_instance.loop
            )
            msg_record["delivered"] = True
            save_messages()
            return jsonify({"status": "sent", "id": msg_record["id"]})
        else:
            return jsonify({
                "status": "queued",
                "id": msg_record["id"],
                "warning": "Bot not connected or channel not configured"
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/claude/read', methods=['GET'])
def read_messages():
    """
    Read recent messages from Claude chat.

    Query params:
        limit: int (default 20)
        since: ISO timestamp (optional)
        from_claude: filter by sender (optional)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        since = request.args.get('since')
        from_filter = request.args.get('from_claude')

        messages = message_store.copy()

        # Filter by timestamp
        if since:
            messages = [m for m in messages if m['timestamp'] > since]

        # Filter by sender
        if from_filter:
            messages = [m for m in messages if m['from_claude'] == from_filter]

        # Return most recent
        return jsonify({
            "messages": messages[-limit:],
            "total": len(messages),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def send_to_discord(message, reply_to=None):
    """Send message to Discord claude-chat channel"""
    try:
        if not bot_instance or not CLAUDE_CHAT_CHANNEL_ID:
            print("Cannot send: bot not ready or channel not configured")
            return False

        channel = bot_instance.get_channel(int(CLAUDE_CHAT_CHANNEL_ID))
        if not channel:
            channel = await bot_instance.fetch_channel(int(CLAUDE_CHAT_CHANNEL_ID))

        if channel:
            await channel.send(message[:2000])
            print(f"Sent to Discord: {message[:100]}...")
            return True
        else:
            print(f"Channel {CLAUDE_CHAT_CHANNEL_ID} not found")
            return False

    except Exception as e:
        print(f"Discord send error: {e}")
        return False

def set_bot_instance(bot):
    """Called from bot.py to link the Discord bot"""
    global bot_instance
    bot_instance = bot
    print(f"Claude API linked to bot: {bot.user}")

def start_api_server():
    """Start Flask server in background thread"""
    load_messages()

    def run():
        print(f"Claude API starting on port {CLAUDE_API_PORT}...")
        app.run(host='0.0.0.0', port=CLAUDE_API_PORT, threaded=True, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print(f"Claude API server started on port {CLAUDE_API_PORT}")
    return thread

# ==================== CHANNEL WATCHER ====================
# Watch #claude-chat for incoming messages (from other bots)

async def watch_claude_channel(bot):
    """Watch the Claude chat channel and store incoming messages"""
    global bot_instance
    bot_instance = bot

    if not CLAUDE_CHAT_CHANNEL_ID:
        print("CLAUDE_CHAT_CHANNEL_ID not configured - channel watcher disabled")
        return

    print(f"Watching Claude chat channel: {CLAUDE_CHAT_CHANNEL_ID}")

    # The actual message capture happens in on_message in bot.py
    # This function just ensures the watcher is initialized

def record_channel_message(message):
    """Record a message from the Claude chat channel"""
    # Parse the [from_claude]: format
    content = message.content
    from_claude = "unknown"

    if content.startswith('[') and ']: ' in content:
        parts = content.split(']: ', 1)
        from_claude = parts[0][1:]  # Remove leading [
        content = parts[1] if len(parts) > 1 else content

    msg_record = {
        "id": str(message.id),
        "from_claude": from_claude,
        "message": content,
        "timestamp": message.created_at.isoformat(),
        "discord_author": str(message.author),
        "reply_to": str(message.reference.message_id) if message.reference else None
    }

    # Avoid duplicates
    if not any(m['id'] == msg_record['id'] for m in message_store):
        message_store.append(msg_record)
        save_messages()
        print(f"Recorded message from {from_claude}: {content[:50]}...")

# ==================== INTEGRATION ====================
"""
To integrate with UnityBot, add to bot.py:

1. At the top:
   from claude_api import start_api_server, set_bot_instance, record_channel_message, CLAUDE_CHAT_CHANNEL_ID

2. In on_ready():
   start_api_server()
   set_bot_instance(bot)

3. In on_message(), before processing:
   if str(message.channel.id) == CLAUDE_CHAT_CHANNEL_ID:
       record_channel_message(message)

4. Add to .env:
   CLAUDE_CHAT_CHANNEL_ID=your_channel_id
   CLAUDE_API_PORT=5050
"""

if __name__ == '__main__':
    # Test mode - run standalone
    print("Running Claude API in test mode...")
    load_messages()
    app.run(host='0.0.0.0', port=CLAUDE_API_PORT, debug=True)
