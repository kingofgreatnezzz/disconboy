# 🔑 DISCORD AUTHORIZATION TOKEN SETUP GUIDE

## 🎯 WHAT THIS DOES
- **Bypasses login forms completely**
- **Skips captchas entirely**
- **No more "account accessed elsewhere" warnings**
- **Direct access to Discord web interface**

## 📋 HOW TO GET YOUR AUTH TOKEN

### Method 1: Browser Developer Tools (Recommended)
1. **Open Discord in your browser** (https://discord.com/app)
2. **Login to your account**
3. **Press F12** to open Developer Tools
4. **Go to Console tab**
5. **Type this command and press Enter:**
   ```javascript
   window.webpackChunkdiscord_app.push([[Math.random()], {}, (req) => {for (const m of Object.keys(req.c).map((x) => req.c[x].exports).filter((x) => x)) {if (m.default && m.default.getToken !== undefined) {return copy(m.default.getToken())}if (m.getToken !== undefined) {return copy(m.getToken())}}}]); console.log('%cWorked!', 'font-size: 50px; color: green;'); console.log(`%cYou now have your token in the clipboard!`, 'font-size: 16px;')
   ```
6. **Copy the token** that appears in console

### Method 2: Network Tab
1. **Open Discord in browser**
2. **Login to your account**
3. **Press F12 → Network tab**
4. **Refresh the page**
5. **Look for requests to discord.com**
6. **Find the request with "authorization" header**
7. **Copy the token value**

## 🔧 SETUP IN YOUR SCRIPT

### Option 1: Environment Variable (Recommended)
```bash
# Windows PowerShell
$env:DISCORD_AUTH_TOKEN="your_token_here"

# Windows CMD
set DISCORD_AUTH_TOKEN=your_token_here

# Linux/Mac
export DISCORD_AUTH_TOKEN="your_token_here"
```

### Option 2: .env File
Create a `.env` file in your project folder:
```env
DISCORD_AUTH_TOKEN=your_token_here
DISCORD_EMAIL=your_email@example.com
DISCORD_PASSWORD=your_password
```

## ⚠️ SECURITY NOTES
- **NEVER share your token publicly**
- **Tokens can expire** - you may need to refresh them
- **Use environment variables** instead of hardcoding
- **Tokens give full access** to your Discord account

## 🚀 RUN THE SCRIPT
```bash
python playwright_discord_monitor.py
```

## ✅ WHAT HAPPENS NOW
1. **Script detects your auth token**
2. **Bypasses login completely**
3. **Goes straight to Discord app**
4. **No captchas or security warnings**
5. **Browser stays open for monitoring**

## 🔄 IF TOKEN EXPIRES
- **Get a new token** using the same method
- **Update your environment variable**
- **Restart the script**

---
**💡 TIP:** The authorization token method is much more reliable than username/password login!
