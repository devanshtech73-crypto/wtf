import os
import random
import string
import threading
import asyncio
from discord.ext import commands
from javascript import require
from dotenv import load_dotenv

# Load Mineflayer
mineflayer = require('mineflayer')
load_dotenv()

class MCWorker:
    """Handles individual Minecraft bot logic"""
    def __init__(self, host, username, version="1.20.1"):
        self.host = host
        self.username = username
        self.version = version
        self.bot = None

    def start(self):
        self.bot = mineflayer.createBot({
            'host': self.host,
            'username': self.username,
            'auth': 'offline',
            'version': self.version
        })

        @self.bot.on('spawn')
        def on_spawn(*args):
            print(f" [MC] {self.username} joined {self.host}")
            # Auto-register logic for cracked servers
            self.bot.chat(f"/register Pass123! Pass123!")
            self.bot.chat(f"/login Pass123!")

        @self.bot.on('kicked')
        def on_kicked(reason, *args):
            print(f" [MC] {self.username} kicked: {reason}")

class SuperController(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, self_bot=True)
        self.active_workers = []

    async def on_ready(self):
        print(f"Discord Self-bot active: {self.user}")

    @commands.command()
    async def join(self, ctx, amount: int, server_ip: str):
        await ctx.message.delete() # Hide the command for safety
        
        for i in range(amount):
            # Generate unique cracked username
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            username = f"Gamer_{suffix}"
            
            # Run Mineflayer in a separate thread to prevent Discord lag
            worker = MCWorker(server_ip, username)
            threading.Thread(target=worker.start, daemon=True).start()
            
            self.active_workers.append(worker)
            await asyncio.sleep(1.5) # Prevent aggressive join throttle
            
        print(f"Sent {amount} bots to {server_ip}")

# --- Initialization ---
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("CRITICAL: No TOKEN found in environment variables.")
    os._exit(1)

bot = SuperController(command_prefix="/")

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Failed to start: {e}")
        
