import discord
import re
import asyncio
import json
import os
import time
from playwright.async_api import async_playwright
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# BOT CONFIGURATION
TOKEN = os.getenv("BOT_TOKEN")
print(f"[DEBUG] BOT TOKEN: {repr(TOKEN)}")

# DISCORD LOGIN CREDENTIALS (for auto-login)
DISCORD_EMAIL = os.getenv("DISCORD_EMAIL")
DISCORD_PASSWORD = os.getenv("DISCORD_PASSWORD")
DISCORD_AUTH_TOKEN = os.getenv("DISCORD_AUTH_TOKEN")  # User authorization token (bypasses login)
DISCORD_CHANNEL_URLS = os.getenv("DISCORD_CHANNEL_URLS")  # User authorization token (bypasses login)
DISCORD_STORAGE_STATE = os.getenv("DISCORD_STORAGE_STATE")  # User authorization token (bypasses login)
PLAYWRIGHT_INSPECTOR = os.getenv("PLAYWRIGHT_INSPECTOR", "0")
MEMBER_SCAN_ENABLED = os.getenv("MEMBER_SCAN_ENABLED", "1")
SEND_MESSAGE_TO_USERS = os.getenv("SEND_MESSAGE_TO_USERS", "0")

# DEBUG: Check if credentials are loaded
print(f"[DEBUG] DISCORD_EMAIL: {repr(DISCORD_EMAIL)}")
print(f"[DEBUG] DISCORD_PASSWORD: {repr(DISCORD_PASSWORD)}")
print(f"[DEBUG] DISCORD_AUTH_TOKEN: {'YES' if DISCORD_AUTH_TOKEN else 'NO'}")
print(f"[DEBUG] Credentials loaded: {'YES' if DISCORD_EMAIL and DISCORD_PASSWORD else 'NO'}")
print(f"[DEBUG] Auth token available: {'YES' if DISCORD_AUTH_TOKEN else 'NO'}")
print(f"[DEBUG] Auth token available: {'YES' if DISCORD_CHANNEL_URLS else 'NO'}")
print(f"[DEBUG] Auth token available: {'YES' if DISCORD_STORAGE_STATE else 'NO'}")
print(f"[DEBUG] Inspector enabled: {'YES' if PLAYWRIGHT_INSPECTOR in ['1','true','TRUE','yes','YES'] else 'NO'}")
print(f"[DEBUG] Member scan enabled: {'YES' if MEMBER_SCAN_ENABLED in ['1','true','TRUE','yes','YES'] else 'NO'}")
print(f"[DEBUG] Send message to users: {'YES' if SEND_MESSAGE_TO_USERS in ['1','true','TRUE','yes','YES'] else 'NO'}")

# NOTIFICATION CHANNEL (where bot sends you updates)
NOTIFICATION_CHANNEL_ID = 1255771048889286703

# WELCOME CHANNEL KEYWORDS FOR SMART DETECTION
WELCOME_CHANNEL_KEYWORDS = [
    "general", "welcome", "new-users", "introductions", "announcements",
    "new-members", "greetings", "hello", "join", "arrivals", "newcomers",
    "intros", "meet", "say-hi", "first-time", "beginners"
]

# JOIN PATTERNS TO DETECT
JOIN_PATTERNS = [
    r"(welcome|joined|just arrived|say hi to|new member|hey everyone welcome) @?([^\s#@]+)",
    r"(please welcome|introduce yourself to) @?([^\s#@]+)",
    r"@?([^\s#@]+) (has joined|is here|just arrived)",
    r"everyone welcome @?([^\s#@]+)",
    r"(new validator|validator joined|staking node|node operator) @?([^\s#@]+)",
    r"(welcome|joined) @?([^\s#@]+) (validator|node|staking|infrastructure)",
    r"@?([^\s#@]+) (joined|arrived) (validator|node|staking) (community|network)",
    r"(ethereum|eth) (validator|node|operator) @?([^\s#@]+) (joined|welcome)",
    r"(new member|welcome) @?([^\s#@]+) (ethereum|eth|blockchain) (community|network)",
    # Discord-specific patterns
    r"welcome to \*([^*]+)\* <@!(\d+)>!",
    r"welcome to ([^!]+)! we are at (\d+) members",
    r"welcome <@!(\d+)> to ([^!]+)!",
    r"([^!]+) joined the server",
    r"welcome ([^!]+) to ([^!]+)"
]

# TARGET SERVERS TO MONITOR
TARGET_SERVERS = [
    "melonly", "midjourney", "BASI AI", "roblox"
]

# RATE LIMITING FOR STEALTH
RATE_LIMIT_DELAY = 2
MAX_OPERATIONS_PER_HOUR = 50

# CHANNEL POLLING CONFIG
# Prefer providing a comma-separated env var DISCORD_CHANNEL_URLS; falls back to this list
CHANNEL_URLS = [
    # Example: "https://discord.com/channels/1039659131067449496/1039661470960595054",
]
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
MESSAGES_PER_CHANNEL_SCAN = int(os.getenv("MESSAGES_PER_CHANNEL_SCAN", "5"))

# STORAGE STATE (Playwright session)
STORAGE_STATE_PATH = os.getenv("DISCORD_STORAGE_STATE", "discordState.json")
print(f"[DEBUG] Storage state path: {STORAGE_STATE_PATH} | Exists: {os.path.exists(STORAGE_STATE_PATH)}")

def load_channel_urls():
    env_urls = os.getenv("DISCORD_CHANNEL_URLS", "").strip()
    urls = []
    if env_urls:
        parts = [p.strip() for p in env_urls.split(",") if p.strip()]
        for part in parts:
            if part.startswith("http"):
                urls.append(part)
    if not urls:
        urls = CHANNEL_URLS.copy()
    print(f"[CONFIG] Loaded {len(urls)} channel URL(s) for monitoring.")
    return urls

print("🚀 PLAYWRIGHT DISCORD MONITOR STARTING...")

# BOT SETUP
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# CACHE FOR PROCESSED MESSAGES
processed_messages = set()
known_users_per_server = defaultdict(set)

def save_cache():
    data = {
        "processed_messages": list(processed_messages),
        "known_users": {str(server): list(users) for server, users in known_users_per_server.items()}
    }
    with open("playwright_monitor_cache.json", "w") as f:
        json.dump(data, f)
    print("[CACHE] Saved to disk.")

def load_cache():
    global processed_messages, known_users_per_server
    if not os.path.exists("playwright_monitor_cache.json"):
        print("[CACHE] No cache file found, starting fresh.")
        return
    
    with open("playwright_monitor_cache.json", "r") as f:
        data = json.load(f)
    processed_messages = set(data.get("processed_messages", []))
    known_users_per_server = defaultdict(set, {server: set(users) for server, users in data.get("known_users", {}).items()})
    print(f"[CACHE] Loaded: {len(processed_messages)} messages, {len(known_users_per_server)} servers.")

def find_join_username(message_content):
    """Extract username from join patterns"""
    for pattern in JOIN_PATTERNS:
        match = re.search(pattern, message_content, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 2 and match.group(2).isdigit():
                return f"User ID: {match.group(2)}"
            elif len(match.groups()) >= 2:
                return match.group(2)
            else:
                return match.group(1)
    return None

async def extract_member_usernames(page):
    """Use the right-side member list to extract visible usernames."""
    names = []
    # Try to open the member list if it's collapsed
    try:
        toggle = page.get_by_label("Show Member List")
        if await toggle.count() > 0:
            try:
                await toggle.first.click()
                await asyncio.sleep(1)
            except Exception:
                pass
    except Exception:
        pass

    # Try to locate the member list container
    candidates = [
        page.get_by_role("list", name=re.compile("members", re.IGNORECASE)),
        page.locator('[aria-label*="Members" i]'),
        page.locator('[role="list"][aria-label]')
    ]

    container = None
    for c in candidates:
        try:
            if await c.count() > 0:
                container = c.first
                break
        except Exception:
            continue

    if not container:
        # Fallback: search common member tiles
        items = page.locator('[role="listitem"]')
    else:
        items = container.get_by_role("listitem")

    try:
        count = await items.count()
    except Exception:
        count = 0

    for i in range(min(count, 500)):
        try:
            text = await items.nth(i).inner_text()
        except Exception:
            continue
        if not text:
            continue
        # Heuristic: first non-empty line tends to be the username
        parts = [p.strip() for p in text.splitlines() if p.strip()]
        if not parts:
            continue
        candidate = parts[0]
        # Clean common noise terms
        noise = {"online", "offline", "idle", "do not disturb", "streaming"}
        if candidate.lower() in noise and len(parts) > 1:
            candidate = parts[1]
        if candidate and len(candidate) <= 64:
            names.append(candidate)

    # Deduplicate while preserving order
    seen = set()
    unique_names = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique_names.append(n)
    return unique_names

async def extract_real_member_usernames(page, limit=20):
    """Click each member tile and read the real username (e.g. @handle) from profile popover."""
    real_names = []

    # Ensure member list visible
    try:
        toggle = page.get_by_label("Show Member List")
        if await toggle.count() > 0:
            try:
                await toggle.first.click()
                await asyncio.sleep(500/1000)
            except Exception:
                pass
    except Exception:
        pass

    # Member list items
    container_candidates = [
        page.get_by_role("list", name=re.compile("members", re.IGNORECASE)),
        page.locator('[aria-label*="Members" i]'),
        page.locator('[role="list"][aria-label]')
    ]

    container = None
    for c in container_candidates:
        try:
            if await c.count() > 0:
                container = c.first
                break
        except Exception:
            continue

    if not container:
        items = page.locator('[role="listitem"]')
    else:
        items = container.get_by_role("listitem")

    try:
        total = await items.count()
    except Exception:
        total = 0

    max_scan = min(limit, total)
    for i in range(max_scan):
        try:
            entry = items.nth(i)
            await entry.click()
            await asyncio.sleep(400/1000)

            # Popover/dialog candidates
            pop_candidates = [
                page.locator('[role="dialog"]'),
                page.locator('[class*="userPopout" i]'),
                page.locator('[aria-label*="User" i]'),
            ]
            pop = None
            for pc in pop_candidates:
                try:
                    if await pc.count() > 0:
                        pop = pc.first
                        break
                except Exception:
                    continue

            if pop is None:
                # Try again lightly
                await asyncio.sleep(300/1000)
                continue

            # Extract @handle or canonical username
            selectors = [
                '[class*="username" i]',
                '[class*="userTag" i]',
                'text=/^@/i',
            ]
            uname = None
            for sel in selectors:
                try:
                    node = pop.locator(sel)
                    if await node.count() > 0:
                        text = (await node.first.inner_text()).strip()
                        if text:
                            uname = text
                            break
                except Exception:
                    continue

            if not uname:
                # Fallback: combine name + discriminator if present
                try:
                    name_node = pop.locator('[class*="name" i]').first
                    disc_node = pop.locator('[class*="discriminator" i]').first
                    if await name_node.count() > 0:
                        base = (await name_node.inner_text()).strip()
                        if await disc_node.count() > 0:
                            disc = (await disc_node.inner_text()).strip()
                            uname = f"{base}{disc}"
                        else:
                            uname = base
                except Exception:
                    pass

            if uname:
                # Normalize @ prefix if missing but looks like a handle
                cleaned = uname.strip()
                if cleaned and not cleaned.startswith("@") and re.match(r"^[A-Za-z0-9._]{2,32}$", cleaned):
                    cleaned = f"@{cleaned}"
                real_names.append(cleaned)

            # Close popover: ESC
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(200/1000)
            except Exception:
                pass
        except Exception:
            continue

    # Deduplicate
    seen = set()
    uniq = []
    for n in real_names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq

async def detect_new_members(server_name, channel_name, usernames):
    """Compare scraped usernames to cache and notify on new ones."""
    newly_detected = []
    known_set = known_users_per_server[server_name]
    for u in usernames:
        if u not in known_set:
            known_set.add(u)
            newly_detected.append(u)
    if newly_detected:
        for u in newly_detected:
            await process_new_user_detection(u, server_name, channel_name, "Detected via member list UI")
        save_cache()

def get_tailored_welcome_message(username, server_name, channel_name):
    """Generate tailored welcome message based on server context"""
    server_lower = server_name.lower()
    channel_lower = channel_name.lower()
    
    # Server-specific messages
    if "melonly" in server_lower:
        return (
            f"🌟 Welcome {username} to Melonly! "
            f"Great to have you join our community! "
            "Feel free to introduce yourself and ask any questions. "
            "We're excited to see what you'll bring to the server! 🚀"
        )
    elif "midjourney" in server_lower:
        return (
            f"🎨 Welcome {username} to the Midjourney community! "
            f"Ready to explore the world of AI-generated art? "
            "Share your creations, get inspired, and connect with fellow artists. "
            "Let's create something amazing together! ✨"
        )
    elif "basi" in server_lower or "ai" in server_lower:
        return (
            f"🤖 Welcome {username} to the AI community! "
            f"Excited to have another AI enthusiast join {server_name}! "
            "Whether you're building, learning, or exploring AI, "
            "this is the perfect place to connect and grow. "
            "Let's push the boundaries of what's possible! 🚀"
        )
    elif "roblox" in server_lower:
        return (
            f"🎮 Welcome {username} to the Roblox community! "
            f"Ready to build, play, and create amazing experiences? "
            "Connect with fellow developers and gamers. "
            "Let's make some incredible games together! 🎯"
        )
    
    # Channel-specific messages
    elif "general" in channel_lower:
        return (
            f"👋 Hey {username}! Welcome to {server_name}! "
            "Great to have you here. Feel free to introduce yourself and ask any questions! 🚀"
        )
    elif "welcome" in channel_lower:
        return (
            f"🎉 Welcome {username} to {server_name}! "
            "We're so excited you've joined us! "
            "Take a look around, introduce yourself, and make some new friends. "
            "This community is amazing and you're going to love it here! 💫"
        )
    elif "introductions" in channel_lower:
        return (
            f"🌟 Welcome {username} to {server_name}! "
            "This is the perfect place to introduce yourself to the community. "
            "Tell us a bit about yourself and what brings you here. "
            "We can't wait to get to know you better! 🤝"
        )
    
    # Default welcome message
    else:
        return (
            f"🎊 Welcome {username} to {server_name}! "
            "You're joining an amazing community of people. "
            "Feel free to explore, ask questions, and connect with fellow members. "
            "We're glad you're here and can't wait to see what you'll contribute! 🚀"
        )

async def send_notification(message_content, is_error=False):
    """Send notification to your notification channel"""
    try:
        notification_channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
        if notification_channel:
            prefix = "🚨 **BOT NOTIFICATION**" if is_error else "📱 **PLAYWRIGHT MONITOR**"
            formatted_msg = f"{prefix}\n\n{message_content}"
            await notification_channel.send(formatted_msg)
            print(f"[NOTIFICATION] Sent to #{notification_channel.name}")
            print("*" *20)
            return True
        else:
            print(f"[ERROR] Could not find notification channel {NOTIFICATION_CHANNEL_ID}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send notification: {e}")
        return False

print("🚀 Playwright Discord Monitor setup complete!")

async def process_new_user_detection(username, server_name, channel_name, message_content):
    """Process new user detection and send welcome message"""
    if f"{username}_{server_name}_{channel_name}" in processed_messages:
        return
    
    print(f"[DETECTION] 🎯 NEW USER DETECTED! Username: '{username}' in #{channel_name} ({server_name})")
    processed_messages.add(f"{username}_{server_name}_{channel_name}")
    
    # Generate tailored welcome message
    welcome_msg = get_tailored_welcome_message(username, server_name, channel_name)
    
    # Send detection notification to you
    detection_msg = (
        f"🎯 **NEW USER DETECTED!**\n\n"
        f"**Username:** {username}\n"
        f"**Server:** {server_name}\n"
        f"**Channel:** #{channel_name}\n"
        f"**Message:** {message_content[:100]}{'...' if len(message_content) > 100 else ''}\n\n"
        f"📤 **Generated Welcome Message:**\n{welcome_msg}"
    )
    
    await send_notification(detection_msg)
    
    # Try to send welcome message to the new user (guarded by flag; currently off)
    try:
        if SEND_MESSAGE_TO_USERS in ["1","true","TRUE","yes","YES"]:
            # Placeholder for future DM logic
            pass
        
        # Send success notification
        print(f"[SUCCESS] Would send welcome message to {username}: {welcome_msg}")
        success_msg = (
            f"✅ **WELCOME MESSAGE READY!**\n\n"
            f"**To:** {username}\n"
            f"**In Server:** {server_name}\n"
            f"**Channel:** #{channel_name}\n"
            f"**Message:** {welcome_msg}\n\n"
            f"**Note:** Welcome message generated and ready to send!"
        )
        await send_notification(success_msg)
        
    except Exception as e:
        error_msg = (
            f"❌ **FAILED TO PROCESS WELCOME**\n\n"
            f"**Username:** {username}\n"
            f"**Error:** {str(e)}\n"
            f"**Possible reasons:**\n"
            f"• User not found in server\n"
            f"• Bot permissions\n"
            f"• Server settings"
        )
        await send_notification(error_msg)
        print(f"[ERROR] Failed to process welcome for {username}: {e}")
    
    save_cache()

async def start_playwright_monitoring():
    """Start the Playwright monitoring process"""
    print("[MONITOR] Starting Playwright monitoring...")
    
    async with async_playwright() as p:
        browser = None
        context = None
        page = None
        
        try:
            # Launch Chromium and load storage state if present
            print("[PLAYWRIGHT] 🧭 Launching Chromium...")
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor"
                ]
            )
            if os.path.exists(STORAGE_STATE_PATH):
                print(f"[PLAYWRIGHT] 💾 Using saved storage state: {STORAGE_STATE_PATH}")
                context = await browser.new_context(storage_state=STORAGE_STATE_PATH)
            else:
                print("[PLAYWRIGHT] ⚠️ Storage state not found. Continuing without it.")
                context = await browser.new_context()
            page = await context.new_page()
            
            # Set viewport and user agent
            await page.set_viewport_size({"width": 1280, "height": 720})
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
            })
            print("[PLAYWRIGHT] ✅ Browser launched successfully!")
            
            # Step 1: Navigate and monitor configured channels
            print("[PLAYWRIGHT] 🌐 Preparing Discord monitoring with configured channels...")
            page.set_default_timeout(60000)

            def parse_titles(title_text: str):
                # Discord title pattern often: "#channel-name - Server Name - Discord"
                if not title_text:
                    return ("Current Server", "Current Channel")
                parts = [p.strip() for p in title_text.split("-")]
                # Try to infer from leftmost parts
                if len(parts) >= 2:
                    channel_part = parts[0].lstrip("#").strip()
                    server_part = parts[1].strip()
                    if channel_part:
                        return (server_part or "Current Server", channel_part or "Current Channel")
                return ("Current Server", "Current Channel")

            channel_urls = load_channel_urls()
            if not channel_urls:
                print("[PLAYWRIGHT] ⚠️ No channel URLs configured. Set DISCORD_CHANNEL_URLS or add to CHANNEL_URLS list.")

            print("[PLAYWRIGHT] 📡 Starting message monitoring over configured channels...")
            inspector_paused_once = False
            while True:
                try:
                    for channel_url in channel_urls:
                        try:
                            print(f"[PLAYWRIGHT] 🔗 Navigating to channel: {channel_url}")
                            try:
                                await page.goto(channel_url, wait_until="networkidle", timeout=60000)
                            except Exception:
                                print("[PLAYWRIGHT] ⏳ Initial load failed. Retrying with reload...")
                                await page.reload()
                                await asyncio.sleep(5)

                            # Wait for messages to be present
                            await asyncio.sleep(5)
                            title_text = await page.title()
                            server_name, channel_name = parse_titles(title_text)
                            print(f"[PLAYWRIGHT] 📍 Now at: {server_name} / #{channel_name}")

                            # Optional one-time inspector pause
                            if (not inspector_paused_once) and (PLAYWRIGHT_INSPECTOR in ["1","true","TRUE","yes","YES"]):
                                print("[PLAYWRIGHT] ⏸ Opening Playwright Inspector (one-time). Explore the UI, then resume...")
                                try:
                                    await page.pause()
                                except Exception as _e:
                                    print(f"[PLAYWRIGHT] ⚠️ Inspector pause failed: {_e}")
                                inspector_paused_once = True

                            locator = page.locator('[class*="messageContent"]')
                            try:
                                count = await locator.count()
                            except Exception:
                                count = 0
                            print(f"[PLAYWRIGHT] 💬 Visible messages: {count}")

                            start_index = max(0, count - MESSAGES_PER_CHANNEL_SCAN)
                            for i in range(start_index, count):
                                try:
                                    text = await locator.nth(i).inner_text()
                                except Exception:
                                    continue
                                if not text:
                                    continue
                                username = find_join_username(text)
                                if username:
                                    print(f"[PLAYWRIGHT] 🎯 JOIN PATTERN DETECTED! Username: {username}")
                                    print(f"[PLAYWRIGHT] 📝 Message: {text[:120]}{'...' if len(text) > 120 else ''}")
                                    await process_new_user_detection(username, server_name, channel_name, text)

                            # Member scan (optional)
                            if MEMBER_SCAN_ENABLED in ["1","true","TRUE","yes","YES"]:
                                try:
                                    usernames = await extract_member_usernames(page)
                                    if usernames:
                                        preview_count = min(20, len(usernames))
                                        print(f"[MEMBERS] Preview of first {preview_count} usernames:")
                                        try:
                                            for idx, name in enumerate(usernames[:20], start=1):
                                                print(f"  {idx}. {name}")
                                        except Exception:
                                            # Fallback single-line print if needed
                                            print(", ".join(usernames[:20]))

                                        # Real usernames via popover (first 20)
                                        try:
                                            real_usernames = await extract_real_member_usernames(page, limit=20)
                                            if real_usernames:
                                                rcount = min(20, len(real_usernames))
                                                print(f"[MEMBERS] Real usernames (first {rcount}):")
                                                for idx, name in enumerate(real_usernames[:20], start=1):
                                                    print(f"  {idx}. {name}")
                                        except Exception as e:
                                            print(f"[PLAYWRIGHT] ⚠️ Real username scan error: {e}")

                                        await detect_new_members(server_name, channel_name, usernames)
                                except Exception as e:
                                    print(f"[PLAYWRIGHT] ⚠️ Member scan error: {e}")

                            await asyncio.sleep(RATE_LIMIT_DELAY)
                        except Exception as e:
                            print(f"[PLAYWRIGHT] ⚠️ Channel navigation/scan error: {e}")
                            await asyncio.sleep(RATE_LIMIT_DELAY)

                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                except KeyboardInterrupt:
                    print("\n[PLAYWRIGHT] 🛑 Interrupted by user (Ctrl+C)")
                    break
                except Exception as e:
                    print(f"[PLAYWRIGHT] ⚠️ Monitoring loop error: {e}")
                    await asyncio.sleep(10)
                
        except Exception as e:
            print(f"[ERROR] Critical Playwright error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                if context:
                    print("[PLAYWRIGHT] 🧹 Closing context...")
                    await context.close()
            except Exception:
                pass
            if browser:
                print("[PLAYWRIGHT] 🚪 Closing browser...")
                await browser.close()
                print("[PLAYWRIGHT] ✅ Browser closed and cleanup complete!")
            else:
                print("[PLAYWRIGHT] ⚠️ No browser to close")

@client.event
async def on_ready():
    print(f"[READY] Logged in as {client.user} ({client.user.id})")
    print(f"[READY] Playwright Discord Monitor is online!")
    
    load_cache()
    
    # Send startup notification
    startup_msg = (
        f"🚀 **PLAYWRIGHT DISCORD MONITOR IS ONLINE!**\n\n"
        f"**Bot Account:** {client.user.name}#{client.user.discriminator}\n"
        f"**Monitoring Method:** Playwright Web Automation\n"
        f"**Welcome Channels:** {len(WELCOME_CHANNEL_KEYWORDS)} keywords\n"
        f"**Join Patterns:** {len(JOIN_PATTERNS)} patterns\n\n"
        f"✅ **Ready to monitor external servers for new users!**\n"
        f"🔍 **Smart channel detection:** ACTIVE\n"
        f"🚀 **Tailored welcome messages:** READY\n\n"
        f"**Target Servers:** {', '.join(TARGET_SERVERS)}\n"
        f"**Welcome Channel Keywords:** {', '.join(WELCOME_CHANNEL_KEYWORDS[:5])}..."
    )
    
    await send_notification(startup_msg)
    print("[READY] Bot is ready and Playwright monitoring is active!")
    
    # Start Playwright monitoring in background
    client.loop.create_task(start_playwright_monitoring())

@client.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author.id == client.user.id:
        return
    
    # Test commands
    if message.content.lower() == "!testplaywright":
        test_msg = (
            f"🧪 **PLAYWRIGHT MONITOR TEST SUCCESSFUL!**\n\n"
            f"**Monitoring Method:** Playwright Web Automation\n"
            f"**Welcome Channels:** {len(WELCOME_CHANNEL_KEYWORDS)} keywords\n"
            f"**Join Patterns:** {len(JOIN_PATTERNS)} patterns\n"
            f"**Target Servers:** {len(TARGET_SERVERS)} servers\n\n"
            f"✅ **Playwright monitoring system operational!**\n"
            f"🚀 **Ready to catch new users via smart web automation!**"
        )
        await message.channel.send(test_msg)
        return
    
    if message.content.lower() == "!channels":
        channels_info = f"**Welcome Channel Keywords Detected:**\n"
        for keyword in WELCOME_CHANNEL_KEYWORDS:
            channels_info += f"🔍 #{keyword}\n"
        
        channels_info += f"\n**Target Servers:**\n"
        for server in TARGET_SERVERS:
            channels_info += f"🎯 {server}\n"
        
        await message.channel.send(channels_info)
        return
    
    if message.content.lower() == "!monitor":
        monitor_msg = (
            f"🔍 **PLAYWRIGHT MONITORING STATUS**\n\n"
            f"**Status:** ACTIVE\n"
            f"**Method:** Web automation via Playwright\n"
            f"**Channels Monitored:** {len(WELCOME_CHANNEL_KEYWORDS)} welcome channel types\n"
            f"**Servers:** {len(TARGET_SERVERS)} target servers\n"
            f"**Rate Limit:** {RATE_LIMIT_DELAY}s between operations\n\n"
            f"✅ **Monitoring external Discord servers for new users!**\n"
            f"🚀 **No bot permissions needed - uses your Discord account!**\n"
            f"⚡ **Playwright advantages:** Auto-waiting, faster, more stable!"
        )
        await message.channel.send(monitor_msg)
        return
    
    if message.content.lower() == "!melonly":
        melonly_msg = (
            f"🎯 **MELONLY SERVER NAVIGATION**\n\n"
            f"**Target Server:** Melonly\n"
            f"**CSS Selector:** `div.stack_dbd263:nth-child(5)`\n"
            f"**Welcome Channels:** Looking for #general, #welcome, #introductions\n\n"
            f"🚀 **Auto-navigation enabled!**\n"
            f"🔍 **Smart channel detection:** ACTIVE\n"
            f"📱 **Browser automation:** RUNNING\n\n"
            f"**Features:**\n"
            f"• Auto-find melonly server icon\n"
            f"• Auto-detect welcome channels\n"
            f"• Smart message pattern recognition\n"
            f"• Tailored welcome messages"
        )
        await message.channel.send(melonly_msg)
        return
    
    if message.content.lower() == "!status":
        status_msg = (
            f"📊 **PLAYWRIGHT MONITOR STATUS**\n\n"
            f"**Bot Status:** ONLINE ✅\n"
            f"**Playwright:** ACTIVE 🚀\n"
            f"**Target:** Melonly Server 🎯\n"
            f"**Channels:** Welcome Detection 🔍\n\n"
            f"**Configuration:**\n"
            f"• Welcome Keywords: {len(WELCOME_CHANNEL_KEYWORDS)}\n"
            f"• Join Patterns: {len(JOIN_PATTERNS)}\n"
            f"• Rate Limit: {RATE_LIMIT_DELAY}s\n"
            f"• Max Operations: {MAX_OPERATIONS_PER_HOUR}/hour\n\n"
            f"**Commands:**\n"
            f"• `!testplaywright` - Test system\n"
            f"• `!channels` - Show keywords\n"
            f"• `!monitor` - Show status\n"
            f"• `!melonly` - Melonly info\n"
            f"• `!status` - This message"
        )
        await message.channel.send(status_msg)
        return

# START THE BOT
if __name__ == "__main__":
    print("🚀 Starting Playwright Discord Monitor 🎉😎 PUTA ...")
    
    try:
        # Start the Discord bot
        client.run(TOKEN)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Received interrupt signal, shutting down...")
    except Exception as e:
        print(f"[ERROR] Bot crashed: {e}")
    finally:
        print("[SHUTDOWN] Playwright Discord Monitor shutdown complete!")
