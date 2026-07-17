import discord
from discord.ext import commands
import os
import asyncio
import json
import logging
import sys
import io
from dotenv import load_dotenv
from datetime import datetime

# ============================================
# FIX: Force UTF-8 for Windows Terminals
# ============================================
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))
OWNER_IDS = [int(id.strip()) for id in os.getenv("OWNER_IDS", "").split(",") if id.strip()]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Global cooldown system
cooldowns = {}

# ============================================
# ADDED: !whoami command to get your User ID
# ============================================
@bot.command()
async def whoami(ctx):
    """Get your Discord user ID"""
    await ctx.send(f"Your User ID is: `{ctx.author.id}`")

# ============================================
# Load cogs
# ============================================
async def load_cogs():
    try:
        await bot.load_extension("cogs.admin_core")
        await bot.load_extension("cogs.game_engine")
        await bot.load_extension("cogs.economy_ultra")
        await bot.load_extension("cogs.leveling_pro")
        await bot.load_extension("cogs.social_interaction")
        await bot.load_extension("cogs.fun_explosion")
        await bot.load_extension("cogs.utility_mega")
        await bot.load_extension("cogs.moderation_elite")
        await bot.load_extension("cogs.music_ultimate")
        await bot.load_extension("cogs.anime_weeb")
        await bot.load_extension("cogs.nsfw_optional")
        await bot.load_extension("cogs.ai_integration")
        await bot.load_extension("cogs.giveaway_raffle")
        await bot.load_extension("cogs.voice_channel")
        await bot.load_extension("cogs.reaction_roles")
        await bot.load_extension("cogs.logging_audit")
        
        # 👇 ADDED: Load the new Ticket Cog 👇
        await bot.load_extension("cogs.ticket")
        
        # 👇 ADDED: Load the new Chat Commands Cog 👇
        await bot.load_extension("cogs.chatcmds")
        
        logging.info("✅ All cogs loaded successfully")
    except Exception as e:
        logging.error(f"❌ Failed to load cogs: {e}")

@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user}")
    logging.info(f"📊 Serving {len(bot.guilds)} guilds")
    logging.info(f"👥 Watching {len(bot.users)} users")
    
    # Set presence
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="VoDevs Support | Tickets"
        )
    )
    
    # Sync slash commands - FIXED WITH BETTER ERROR HANDLING
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            try:
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
                logging.info(f"✅ Commands synced to guild: {GUILD_ID}")
            except discord.Forbidden:
                logging.warning("⚠️ Cannot sync to specific guild (missing permissions). Syncing globally instead.")
                await bot.tree.sync()
                logging.info("✅ Commands synced globally")
        else:
            await bot.tree.sync()
            logging.info("✅ Commands synced globally")
    except discord.Forbidden as e:
        logging.error(f"❌ Failed to sync commands: {e}")
        logging.warning("⚠️ Bot needs 'applications.commands' scope. Re-invite the bot with this scope.")
        logging.warning("📌 Use this invite URL format: https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot+applications.commands")
    except Exception as e:
        logging.error(f"❌ Failed to sync commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f}s.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have permission to do that.")
    else:
        logging.error(f"❌ Command error: {error}")

# Global helper functions
async def delete_message_after_delay(message, delay=5):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(load_cogs())
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        logging.error("❌ Invalid bot token!")
    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")