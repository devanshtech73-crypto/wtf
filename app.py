import discord
from discord.ext import commands
import requests
import re
import asyncio
import io,os
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Suppress SSL warnings
import urllib3
urllib3.disable_warnings()

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")  # Replace with your actual bot token
PREFIX = "!"

# Microsoft login URLs
sFTTag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

# ==================== MICROSOFT ACCOUNT CHECK ====================
def get_urlPost_sFTTag(session):
    """Extract login page tokens"""
    try:
        text = session.get(sFTTag_url, timeout=15).text
        
        # Extract sFTTag (the security token)
        sFTTag = None
        patterns = [
            r'value="([^"]+)" name="PPFT"',
            r'name="PPFT"\s+value="([^"]+)"',
            r'value=\\\"(.+?)\\\"',
            r'value="(.+?)"'
        ]
        
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
                r'action="([^"]+)"'
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, text, re.S)
                if match:
                    return match.group(1), sFTTag, session
        
        return None, None, session
    except Exception as e:
        print(f"Error getting tokens: {e}")
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
        
        # Check for access_token in the URL fragment
        if '#' in login_request.url:
            fragment = urlparse(login_request.url).fragment
            token = parse_qs(fragment).get('access_token', ["None"])[0]
            if token != "None":
                return token, session
        
        # Check for 2FA
        if any(x in login_request.text.lower() for x in ['twofactor', '2fa', 'cancel?mkt=', 'recover?mkt', 'proof']):
            return "2FA", session
        
        # Check for bad credentials
        error_indicators = [
            'password is incorrect',
            "account doesn't exist",
            "that password is incorrect",
            "sign in to your microsoft",
            "we detected something unusual"
        ]
        
        if any(x in login_request.text.lower() for x in error_indicators):
            return "BAD", session
        
        # Sometimes it redirects to a different page
        if 'login.live.com' in login_request.url and 'error' in login_request.url:
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
    """Retrieve Minecraft profile"""
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
        elif resp.status_code == 404:
            return None, None, None
        return None, None, None
        
    except Exception as e:
        print(f"Profile error: {e}")
        return None, None, None

def check_microsoft_account(email, password):
    """Complete account check function"""
    session = requests.Session()
    session.verify = False
    
    try:
        # Step 1: Get login page tokens
        urlPost, sFTTag, session = get_urlPost_sFTTag(session)
        if not urlPost or not sFTTag:
            return {
                "status": "error",
                "message": "Could not load Microsoft login page"
            }
        
        # Step 2: Login
        rps_token, session = get_xbox_rps(session, email, password, urlPost, sFTTag)
        
        if rps_token == "BAD":
            return {
                "status": "bad",
                "message": "❌ Invalid email or password"
            }
        elif rps_token == "2FA":
            return {
                "status": "2fa",
                "message": "🔐 2FA Required - Cannot automate"
            }
        
        # Step 3: Get XSTS token
        uhs, xsts_token = get_xsts_token(session, rps_token)
        if not uhs or not xsts_token:
            return {
                "status": "error",
                "message": "Authentication failed"
            }
        
        # Step 4: Get Minecraft token
        mc_token = get_minecraft_token(session, uhs, xsts_token)
        if not mc_token:
            return {
                "status": "valid_mail",
                "message": "📧 Valid Microsoft Account (No Minecraft)"
            }
        
        # Step 5: Get Minecraft profile
        ign, capes, uuid = get_minecraft_profile(session, mc_token)
        if ign:
            return {
                "status": "hit",
                "ign": ign,
                "capes": capes,
                "uuid": uuid,
                "message": f"✅ **MINECRAFT ACCOUNT!**\nIGN: {ign}\nCapes: {capes}\nUUID: {uuid}"
            }
        else:
            return {
                "status": "error",
                "message": "Profile fetch failed"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }
    finally:
        session.close()

# ==================== DISCORD BOT ====================
bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all(), help_command=None)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}check | Account Checker"))

@bot.command(name="check", aliases=["c"])
async def check_cmd(ctx, *, credentials: str = None):
    """Check a single Microsoft/Minecraft account"""
    if not credentials:
        embed = discord.Embed(
            title="❌ Invalid Usage",
            description=f"Please use: `{PREFIX}check email:password`\n\nExample: `{PREFIX}check test@gmail.com:password123`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if ":" not in credentials:
        embed = discord.Embed(
            title="❌ Invalid Format",
            description="Please use: `email:password`\n\nExample: `test@gmail.com:password123`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    email, password = credentials.split(":", 1)
    
    # Send initial message
    msg = await ctx.send(f"🔍 Checking `{email}`...\nThis may take 10-15 seconds...")
    
    # Run check in thread
    def check():
        return check_microsoft_account(email, password)
    
    result = await asyncio.get_event_loop().run_in_executor(None, check)
    
    # Create response embed
    embed = discord.Embed(title="Account Check Result", color=discord.Color.blue())
    embed.add_field(name="Email", value=email, inline=False)
    
    if result["status"] == "hit":
        embed.color = discord.Color.green()
        embed.add_field(name="Status", value="✅ MINECRAFT ACCOUNT", inline=True)
        embed.add_field(name="IGN", value=result["ign"], inline=True)
        embed.add_field(name="Capes", value=result["capes"], inline=False)
        embed.add_field(name="UUID", value=result["uuid"], inline=False)
        
    elif result["status"] == "valid_mail":
        embed.color = discord.Color.gold()
        embed.add_field(name="Status", value="📧 VALID MICROSOFT ACCOUNT", inline=True)
        embed.add_field(name="Note", value="No Minecraft license found", inline=False)
        
    elif result["status"] == "2fa":
        embed.color = discord.Color.orange()
        embed.add_field(name="Status", value="🔐 2FA REQUIRED", inline=True)
        embed.add_field(name="Note", value="This account has two-factor authentication enabled", inline=False)
        
    elif result["status"] == "bad":
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="❌ INVALID CREDENTIALS", inline=True)
        embed.add_field(name="Note", value="Email or password is incorrect", inline=False)
        
    else:
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value="⚠️ ERROR", inline=True)
        embed.add_field(name="Error", value=result["message"], inline=False)
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="test")
async def test(ctx):
    """Test if bot is working"""
    embed = discord.Embed(
        title="✅ Bot is Working!",
        description=f"Connected to Discord\nLatency: {round(bot.latency * 1000)}ms\nUsing Microsoft login API",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="commands", aliases=["help"])
async def commands_cmd(ctx):
    """Show all commands"""
    embed = discord.Embed(
        title="🤖 MSMC Discord Bot - Commands",
        description="Microsoft/Minecraft Account Checker\nChecks if email:password is valid and has Minecraft",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name=f"{PREFIX}check email:password",
        value="Check a single Microsoft/Minecraft account\nExample: `!check test@gmail.com:pass123`",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}test",
        value="Check if bot is working",
        inline=False
    )
    
    embed.add_field(
        name=f"{PREFIX}commands",
        value="Show this help message",
        inline=False
    )
    
    embed.add_field(
        name="What it checks",
        value="✓ Valid Microsoft account\n✓ Minecraft ownership\n✓ IGN and UUID\n✓ Cape list",
        inline=False
    )
    
    embed.set_footer(text="Made for Minecraft account checking")
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❌ Command Not Found",
            description=f"Use `{PREFIX}commands` to see all commands",
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
        print(f"Error: {error}")

# ==================== RUN BOT ====================
if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("⚠️  BOT TOKEN REQUIRED!")
        print("="*60)
        print("\nTo get your bot token:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Create a new application")
        print("3. Go to 'Bot' section")
        print("4. Click 'Add Bot'")
        print("5. Copy the token")
        print("\nReplace 'YOUR_BOT_TOKEN_HERE' with your actual token")
        print("="*60 + "\n")
        exit(1)
    
    print("Starting MSMC Discord Bot...")
    print("="*40)
    bot.run(TOKEN)
