@echo off
echo 🚀 Setting up Discord Bot with Playwright...
echo.

echo 📦 Installing Python dependencies...
pip install -r others/requirements.txt

echo.
echo 🔧 Installing Playwright browsers...
playwright install firefox

echo.
echo 📝 Creating .env file...
if not exist .env (
    copy env_template.txt .env
    echo ✅ Created .env file - please edit it with your credentials!
) else (
    echo ⚠️ .env file already exists
)

echo.
echo 🎯 Setup complete! Next steps:
echo 1. Edit .env file with your Discord credentials
echo 2. Run: python playwright_discord_monitor.py
echo.
pause
