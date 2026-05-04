import requests
import config as cfg

def test_telegram_connection():
    print(f"Testing Telegram Connection with...")
    print(f"Token: {cfg.TELEGRAM_BOT_TOKEN}")
    print(f"Chat ID: {cfg.TELEGRAM_CHAT_ID}")
    print("-" * 40)
    
    # 1. Test getMe to see if the token is valid
    url_me = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/getMe"
    resp_me = requests.get(url_me)
    if not resp_me.ok:
        print("❌ ERROR: Your Telegram Bot Token appears to be invalid!")
        print(f"Details: {resp_me.text}")
        print("Please check your token in `config.py` (It should look like '1234567890:ABCdEfGhIjK...')")
        return
    else:
        bot_info = resp_me.json().get('result', {})
        print(f"✅ Bot Token is VALID! (Bot Name: @{bot_info.get('username')})")
        
    # 2. Test sendMessage to see if the Chat ID is valid
    url_msg = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": cfg.TELEGRAM_CHAT_ID,
        "text": "✅ *Aether Flow Bot* connection test successful!",
        "parse_mode": "Markdown"
    }
    resp_msg = requests.post(url_msg, json=payload)
    if not resp_msg.ok:
        print("❌ ERROR: Failed to send message to the specified Chat ID.")
        print(f"Details: {resp_msg.text}")
        print("Please make sure you have started a chat with your bot first.")
    else:
        print("✅ Message successfully sent to Telegram! Your connection is ready.")

if __name__ == "__main__":
    test_telegram_connection()
