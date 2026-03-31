import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

# Load your token from a .env file for security
load_dotenv()
TOKEN = os.getenv("TOKEN")

# CONFIGURATION
SOURCE_CHANNEL_ID = 1470409209123176642  # Channel to monitor
DEST_CHANNEL_ID = 1483459286569849066    # Channel to forward to

class EmbedForwarder(commands.Bot):
    def __init__(self):
        # Self-bots usually need all intents, but check library docs for specifics
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", self_bot=True, intents=intents)

    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")
        print("🚀 Starting Historical Sync (Last 100 messages)...")
        await self.sync_old_messages()
        print("📡 Moving to Live Mode...")

    async def forward_embeds(self, message):
        """Helper to extract and forward embeds from a message."""
        if not message.embeds:
            return

        dest_channel = self.get_channel(DEST_CHANNEL_ID)
        if dest_channel:
            for embed in message.embeds:
                try:
                    await dest_channel.send(embed=embed)
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.5) 
                except Exception as e:
                    print(f"❌ Error forwarding: {e}")

    async def sync_old_messages(self):
        """Fetch and forward the last 100 embeds."""
        source_channel = self.get_channel(SOURCE_CHANNEL_ID)
        if not source_channel:
            print("❌ Could not find source channel. Check the ID.")
            return

        # Fetch history (oldest first to maintain order)
        messages = []
        async for msg in source_channel.history(limit=100, oldest_first=True):
            messages.append(msg)
        
        for msg in messages:
            await self.forward_embeds(msg)
        print(f"✨ Historical sync complete. Processed {len(messages)} messages.")

    async def on_message(self, message):
        # Ignore messages not from our source channel
        if message.channel.id != SOURCE_CHANNEL_ID:
            return
        
        # Forward live embeds
        await self.forward_embeds(message)

if __name__ == "__main__":
    bot = EmbedForwarder()
    bot.run(TOKEN)
