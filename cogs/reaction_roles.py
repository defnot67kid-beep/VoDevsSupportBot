import discord
from discord.ext import commands
import json
import os

# ============================================
# DATA MANAGEMENT (Persistent JSON Storage)
# ============================================
DATA_FILE = "reaction_roles.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {} # Format: { "guild_id": { "message_id": { "emoji": { "role_ids": [123, 456], "description": "text" } } } }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ============================================
# THE COG
# ============================================
class ReactionRoles(commands.Cog):
    """Reaction role system with descriptions and multiple roles per emoji"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    def get_guild_data(self, guild_id):
        guild_id_str = str(guild_id)
        if guild_id_str not in self.data:
            self.data[guild_id_str] = {}
        return self.data[guild_id_str]

    def get_message_data(self, guild_id, message_id):
        guild_data = self.get_guild_data(guild_id)
        msg_id_str = str(message_id)
        if msg_id_str not in guild_data:
            guild_data[msg_id_str] = {}
        return guild_data[msg_id_str]

    @commands.group(name="rr", invoke_without_command=True)
    async def rr(self, ctx):
        """Manage reaction roles. Use `!rr setup`, `!rr add`, `!rr remove`"""
        embed = discord.Embed(title="🎭 Reaction Role Help", color=discord.Color.blue())
        embed.add_field(name="!rr setup", value="Replies to a message to start the interactive setup.", inline=False)
        embed.add_field(name="!rr add [MessageID] [Emoji] [Role1] [Role2...] --desc [Text]", value="Manually add roles to an emoji.", inline=False)
        embed.add_field(name="!rr remove [MessageID] [Emoji]", value="Removes an emoji reaction role.", inline=False)
        embed.add_field(name="!rr list", value="Shows all reaction roles in the server.", inline=False)
        await ctx.send(embed=embed)

    # ============================================
    # 1. INTERACTIVE SETUP COMMAND (Easiest way)
    # ============================================
    @rr.command(name="setup")
    @commands.has_permissions(manage_roles=True)
    async def rr_setup(self, ctx):
        """Interactive setup: Reply to the message you want reactions on."""
        await ctx.send("📌 **Reply to this message with the ID or link of the message** you want to add reaction roles to.\n*(Example: `https://discord.com/channels/.../123456789`)*")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await self.bot.wait_for('message', timeout=60.0, check=check)
            
            # Parse ID from link or just ID
            message_id = None
            if "channels/" in reply.content:
                # Extract ID from URL
                parts = reply.content.split("/")
                message_id = int(parts[-1])
            else:
                message_id = int(reply.content)

            # Fetch the message
            try:
                target_msg = await ctx.channel.fetch_message(message_id)
            except:
                await ctx.send("❌ Could not find that message. Make sure the bot can see the channel it's in.")
                return

            await ctx.send(f"✅ Found message! Now, **send the Emoji** you want people to react with.")

            emoji_msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            emoji = emoji_msg.content.strip()

            await ctx.send(f"✅ Got emoji! Now, **mention the Role(s)** you want to give. (You can mention multiple).\n*(Example: `@Support @Muted`)*")

            roles_msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            roles = []
            for role_mention in roles_msg.role_mentions:
                roles.append(role_mention.id)

            if not roles:
                await ctx.send("❌ No valid roles mentioned.")
                return
            
            await ctx.send(f"✅ Got roles! Finally, **type a short description** for these roles (or type `none`).")

            desc_msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            description = desc_msg.content if desc_msg.content.lower() != "none" else "No description provided."

            # Save to data
            msg_data = self.get_message_data(ctx.guild.id, target_msg.id)
            msg_data[emoji] = {
                "role_ids": roles,
                "description": description
            }
            save_data(self.data)

            # Add the reaction
            try:
                await target_msg.add_reaction(emoji)
            except:
                await ctx.send("⚠️ Could not add the reaction to the message (Invalid emoji or no permissions).")
            
            await ctx.send(f"✅ **Success!** Reacting with `{emoji}` will now give: {', '.join([r.mention for r in roles_msg.role_mentions])}")

        except asyncio.TimeoutError:
            await ctx.send("⏰ Setup timed out. Please run `!rr setup` again.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")

    # ============================================
    # 2. MANUAL COMMANDS
    # ============================================
    @rr.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def rr_add(self, ctx, message_id: int, emoji: str, *args):
        """Add a reaction role manually. 
        Usage: !rr add 1234567890 🟢 @Role1 @Role2 --desc This is a cool role!
        """
        # Parse --desc flag
        description = "No description provided."
        roles = []
        if "--desc" in args:
            split_idx = args.index("--desc")
            roles = args[:split_idx]
            description = " ".join(args[split_idx+1:])
        else:
            roles = args

        role_ids = []
        role_mentions = []
        # Convert mentions to IDs
        for arg in roles:
            # Try to find role via mention
            role = await commands.RoleConverter().convert(ctx, arg)
            if role:
                role_ids.append(role.id)
                role_mentions.append(role.mention)
            else:
                await ctx.send(f"❌ Could not find role: `{arg}`")
                return

        if not role_ids:
            await ctx.send("❌ You must provide at least one valid role.")
            return

        msg_data = self.get_message_data(ctx.guild.id, message_id)
        msg_data[emoji] = {
            "role_ids": role_ids,
            "description": description
        }
        save_data(self.data)

        try:
            msg = await ctx.channel.fetch_message(message_id)
            await msg.add_reaction(emoji)
            await ctx.send(f"✅ Reaction added: `{emoji}` → {', '.join(role_mentions)}\n**Desc:** {description}")
        except:
            await ctx.send("❌ Failed to find the message or add the reaction. Make sure the ID is correct.")

    @rr.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def rr_remove(self, ctx, message_id: int, emoji: str):
        """Remove an emoji's reaction role"""
        msg_data = self.get_message_data(ctx.guild.id, message_id)
        if emoji in msg_data:
            del msg_data[emoji]
            save_data(self.data)
            await ctx.send(f"✅ Removed reaction role for `{emoji}`.")
        else:
            await ctx.send("❌ That emoji wasn't found on that message.")

    @rr.command(name="list")
    async def rr_list(self, ctx):
        """List all reaction roles in this server"""
        guild_data = self.get_guild_data(ctx.guild.id)
        if not guild_data:
            await ctx.send("❌ No reaction roles set up in this server.")
            return
        
        embed = discord.Embed(title="🎭 Reaction Roles", color=discord.Color.blue())
        embed.set_footer(text="React to the message to get the role(s)!")
        
        count = 0
        for msg_id, reactions in guild_data.items():
            # Try to find channel/message
            msg_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{msg_id}"
            
            field_text = []
            for emoji, data in reactions.items():
                role_mentions = []
                for r_id in data["role_ids"]:
                    role = ctx.guild.get_role(r_id)
                    if role:
                        role_mentions.append(role.mention)
                
                if role_mentions:
                    field_text.append(f"{emoji} → {', '.join(role_mentions)}\n> *{data['description']}*")
            
            if field_text:
                embed.add_field(name=f"Message: [Click Here]({msg_link})", value="\n\n".join(field_text), inline=False)
                count += 1

        if count == 0:
            await ctx.send("❌ No reaction roles found (maybe the roles were deleted?).")
        else:
            await ctx.send(embed=embed)

    # ============================================
    # 3. EVENT LISTENERS (Giving/Taking Roles)
    # ============================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return # Ignore bot's own reactions

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        guild_data = self.get_guild_data(payload.guild_id)
        msg_id_str = str(payload.message_id)

        if msg_id_str in guild_data:
            emoji_str = str(payload.emoji)
            if emoji_str in guild_data[msg_id_str]:
                data = guild_data[msg_id_str][emoji_str]
                
                member = guild.get_member(payload.user_id)
                if not member:
                    return

                roles_to_add = []
                for role_id in data["role_ids"]:
                    role = guild.get_role(role_id)
                    if role and role not in member.roles:
                        roles_to_add.append(role)

                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Reaction Role")
                    except discord.Forbidden:
                        pass # Bot lacks permissions

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        guild_data = self.get_guild_data(payload.guild_id)
        msg_id_str = str(payload.message_id)

        if msg_id_str in guild_data:
            emoji_str = str(payload.emoji)
            if emoji_str in guild_data[msg_id_str]:
                data = guild_data[msg_id_str][emoji_str]
                
                member = guild.get_member(payload.user_id)
                if not member:
                    return

                roles_to_remove = []
                for role_id in data["role_ids"]:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        roles_to_remove.append(role)

                if roles_to_remove:
                    try:
                        await member.remove_roles(*roles_to_remove, reason="Reaction Role Removed")
                    except discord.Forbidden:
                        pass

# ============================================
# SETUP FUNCTION
# ============================================
async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
