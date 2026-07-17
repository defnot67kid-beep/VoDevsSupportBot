import discord
from discord.ext import commands
from discord.ui import Select, View, Modal, TextInput, Button
import asyncio
import secrets
import string
from datetime import datetime, timedelta
import json
import os

# ============================================
# DATA PERSISTENCE
# ============================================

class TicketData:
    def __init__(self):
        self.data_file = "ticket_data.json"
        self.tickets = {}  # channel_id -> ticket_info
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    self.tickets = json.load(f)
            except:
                self.tickets = {}
    
    def save_data(self):
        with open(self.data_file, "w") as f:
            json.dump(self.tickets, f, indent=4)
    
    def create_ticket(self, channel_id, user_id, category, reason, ticket_code):
        self.tickets[str(channel_id)] = {
            "user_id": str(user_id),
            "category": category,
            "reason": reason,
            "ticket_code": ticket_code,
            "created_at": datetime.now().isoformat(),
            "claimed_by": None,
            "status": "open",
            "messages": []
        }
        self.save_data()
    
    def claim_ticket(self, channel_id, staff_id):
        if str(channel_id) in self.tickets:
            self.tickets[str(channel_id)]["claimed_by"] = str(staff_id)
            self.tickets[str(channel_id)]["status"] = "claimed"
            self.save_data()
            return True
        return False
    
    def close_ticket(self, channel_id):
        if str(channel_id) in self.tickets:
            self.tickets[str(channel_id)]["status"] = "closed"
            self.save_data()
            return True
        return False
    
    def get_ticket(self, channel_id):
        return self.tickets.get(str(channel_id))

ticket_data = TicketData()

# ============================================
# TICKET MODAL
# ============================================

class TicketModal(Modal, title="Create a Ticket"):
    def __init__(self, category):
        super().__init__()
        self.category = category
    
    reason_input = TextInput(
        label="What is your issue?",
        style=discord.TextStyle.paragraph,
        placeholder="Please describe your issue in detail...",
        required=True,
        min_length=10,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        category = self.category
        reason = self.reason_input.value
        
        # Check for existing open ticket
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                if member in channel.members:
                    # Check if ticket is still open
                    ticket_info = ticket_data.get_ticket(channel.id)
                    if ticket_info and ticket_info.get("status") != "closed":
                        await interaction.followup.send(
                            f"❌ You already have an open ticket! Please close it first.\n{channel.mention}",
                            ephemeral=True
                        )
                        return
        
        # Generate ticket code
        alphabet = string.ascii_lowercase + string.digits
        while True:
            ticket_code = ''.join(secrets.choice(alphabet) for _ in range(5))
            channel_name = f"ticket-{ticket_code}"
            if not discord.utils.get(guild.channels, name=channel_name):
                break
        
        # Get or create ticket category
        ticket_category = discord.utils.get(guild.categories, name="TICKETS")
        if not ticket_category:
            ticket_category = await guild.create_category("TICKETS")
        
        # Setup permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            member: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }
        
        # Add support roles
        support_role = discord.utils.get(guild.roles, name="Support")
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True
            )
        
        # Create channel
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{ticket_code}",
            category=ticket_category,
            overwrites=overwrites,
            reason=f"Ticket opened by {member}"
        )
        
        # Store ticket data
        ticket_data.create_ticket(
            ticket_channel.id,
            member.id,
            category,
            reason,
            ticket_code
        )
        
        # Send initial ticket embed
        embed = discord.Embed(
            title="🎫 Ticket Created",
            description=f"Ticket created by {member.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="📋 Category",
            value=category,
            inline=True
        )
        embed.add_field(
            name="🆔 Ticket Code",
            value=f"`{ticket_code}`",
            inline=True
        )
        embed.add_field(
            name="📝 Reason",
            value=reason[:500],
            inline=False
        )
        embed.set_footer(text=f"User ID: {member.id}")
        
        # Ticket controls view
        view = TicketControlsView(member.id, ticket_channel.id)
        
        await ticket_channel.send(embed=embed, view=view)
        
        # Send category-specific ping
        ping_role = None
        if category == "Appeals":
            ping_role = discord.utils.get(guild.roles, name="Appeals Team")
        elif category == "Report Player":
            ping_role = discord.utils.get(guild.roles, name="Moderation Team")
        elif category == "Support":
            ping_role = discord.utils.get(guild.roles, name="Support")
        
        if ping_role:
            await ticket_channel.send(f"{ping_role.mention} - A new ticket has been created!", delete_after=5)
        
        # Notify user
        await interaction.followup.send(
            f"✅ Ticket created! Please go to {ticket_channel.mention}",
            ephemeral=True
        )

# ============================================
# TICKET CONTROLS VIEW
# ============================================

class TicketControlsView(View):
    def __init__(self, user_id, channel_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.channel_id = channel_id
        
        # Claim Button
        self.add_item(Button(
            label="Claim",
            style=discord.ButtonStyle.primary,
            custom_id=f"claim_ticket_{channel_id}",
            emoji="📌"
        ))
        
        # Close Button
        self.add_item(Button(
            label="Close",
            style=discord.ButtonStyle.danger,
            custom_id=f"close_ticket_{channel_id}",
            emoji="🔒"
        ))
        
        # Request Closure Button (for users)
        self.add_item(Button(
            label="Request Closure",
            style=discord.ButtonStyle.secondary,
            custom_id=f"request_close_{channel_id}",
            emoji="⏳"
        ))

# ============================================
# TICKET SELECT (DROP DOWN)
# ============================================

class TicketSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Appeals",
                description="Appeal a ban or punishment",
                emoji="⚖️",
                value="Appeals"
            ),
            discord.SelectOption(
                label="Report Player",
                description="Report a player for rule-breaking",
                emoji="🚨",
                value="Report Player"
            ),
            discord.SelectOption(
                label="Support",
                description="General support and assistance",
                emoji="❔",
                value="Support"
            ),
            discord.SelectOption(
                label="Suggestion",
                description="Suggest a new feature or change",
                emoji="💡",
                value="Suggestion"
            ),
            discord.SelectOption(
                label="Report Staff",
                description="Report a staff member",
                emoji="👮",
                value="Report Staff"
            ),
        ]
        super().__init__(
            placeholder="Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_modal(TicketModal(selected))

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ============================================
# MAIN COG
# ============================================

class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlsView(0, 0))
    
    @commands.command(name="ticketsetup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx):
        """[Admin] Deploy the ticket panel"""
        try:
            await ctx.message.delete()
        except:
            pass
        
        # Get or create necessary roles
        guild = ctx.guild
        
        # Support role
        support_role = discord.utils.get(guild.roles, name="Support")
        if not support_role:
            support_role = await guild.create_role(
                name="Support",
                color=discord.Color.blue()
            )
        
        # Moderation role
        mod_role = discord.utils.get(guild.roles, name="Moderation Team")
        if not mod_role:
            mod_role = await guild.create_role(
                name="Moderation Team",
                color=discord.Color.red()
            )
        
        # Appeals role
        appeals_role = discord.utils.get(guild.roles, name="Appeals Team")
        if not appeals_role:
            appeals_role = await guild.create_role(
                name="Appeals Team",
                color=discord.Color.gold()
            )
        
        # Create ticket category
        ticket_category = discord.utils.get(guild.categories, name="TICKETS")
        if not ticket_category:
            ticket_category = await guild.create_category("TICKETS")
        
        # Create ticket logs channel
        logs_channel = discord.utils.get(guild.text_channels, name="ticket-logs")
        if not logs_channel:
            logs_channel = await guild.create_text_channel(
                "ticket-logs",
                category=ticket_category
            )
        
        # Setup ticket panel
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Select a category below to create a ticket.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📋 What type of ticket?",
            value=(
                "**Appeals** - Appeal a ban or punishment\n"
                "**Report Player** - Report a player for rule-breaking\n"
                "**Support** - General support and assistance\n"
                "**Suggestion** - Suggest a new feature or change\n"
                "**Report Staff** - Report a staff member"
            ),
            inline=False
        )
        embed.add_field(
            name="📌 Note",
            value="Please select the most accurate category for faster assistance.",
            inline=False
        )
        embed.set_footer(text="Vortex Support System")
        
        view = TicketPanelView()
        
        await ctx.send(embed=embed, view=view)
        
        # Log setup
        embed_log = discord.Embed(
            title="✅ Ticket System Setup Complete",
            color=discord.Color.green()
        )
        embed_log.add_field(
            name="📋 Roles Created/Found",
            value=(
                f"Support: {support_role.mention}\n"
                f"Moderation Team: {mod_role.mention}\n"
                f"Appeals Team: {appeals_role.mention}"
            ),
            inline=False
        )
        embed_log.add_field(
            name="📁 Category",
            value=ticket_category.mention,
            inline=False
        )
        embed_log.add_field(
            name="📊 Logs Channel",
            value=logs_channel.mention,
            inline=False
        )
        
        await ctx.send(embed=embed_log, delete_after=10)
    
    # ============================================
    # TICKET BUTTON HANDLERS
    # ============================================
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id", "")
        
        # ==========================================
        # CLAIM TICKET
        # ==========================================
        if custom_id.startswith("claim_ticket_"):
            channel_id = int(custom_id.split("_")[2])
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
                return
            
            ticket_info = ticket_data.get_ticket(channel_id)
            if not ticket_info:
                await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
                return
            
            if ticket_info.get("claimed_by"):
                claimed_by = interaction.guild.get_member(int(ticket_info["claimed_by"]))
                await interaction.response.send_message(
                    f"❌ This ticket is already claimed by {claimed_by.mention if claimed_by else 'unknown'}.",
                    ephemeral=True
                )
                return
            
            # Check if user has staff permissions
            support_role = discord.utils.get(interaction.guild.roles, name="Support")
            mod_role = discord.utils.get(interaction.guild.roles, name="Moderation Team")
            appeals_role = discord.utils.get(interaction.guild.roles, name="Appeals Team")
            
            has_permission = False
            if support_role and support_role in interaction.user.roles:
                has_permission = True
            if mod_role and mod_role in interaction.user.roles:
                has_permission = True
            if appeals_role and appeals_role in interaction.user.roles:
                has_permission = True
            if interaction.user.guild_permissions.administrator:
                has_permission = True
            
            if not has_permission:
                await interaction.response.send_message(
                    "❌ You don't have permission to claim tickets.",
                    ephemeral=True
                )
                return
            
            # Claim the ticket
            if ticket_data.claim_ticket(channel_id, interaction.user.id):
                await interaction.response.send_message(
                    f"✅ You have claimed this ticket!",
                    ephemeral=True
                )
                
                # Send notification in channel
                await channel.send(
                    f"📌 {interaction.user.mention} has claimed this ticket."
                )
                
                # Update embed with claimed info
                try:
                    async for msg in channel.history(limit=1):
                        if msg.embeds:
                            embed = msg.embeds[0]
                            embed.add_field(
                                name="👤 Claimed By",
                                value=interaction.user.mention,
                                inline=True
                            )
                            await msg.edit(embed=embed)
                            break
                except:
                    pass
        
        # ==========================================
        # CLOSE TICKET
        # ==========================================
        elif custom_id.startswith("close_ticket_"):
            channel_id = int(custom_id.split("_")[2])
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
                return
            
            # Check if user has permission to close
            support_role = discord.utils.get(interaction.guild.roles, name="Support")
            mod_role = discord.utils.get(interaction.guild.roles, name="Moderation Team")
            appeals_role = discord.utils.get(interaction.guild.roles, name="Appeals Team")
            
            has_permission = False
            if support_role and support_role in interaction.user.roles:
                has_permission = True
            if mod_role and mod_role in interaction.user.roles:
                has_permission = True
            if appeals_role and appeals_role in interaction.user.roles:
                has_permission = True
            if interaction.user.guild_permissions.administrator:
                has_permission = True
            
            # Check if user is the ticket creator
            ticket_info = ticket_data.get_ticket(channel_id)
            is_creator = ticket_info and int(ticket_info["user_id"]) == interaction.user.id
            
            if not has_permission and not is_creator:
                await interaction.response.send_message(
                    "❌ You don't have permission to close this ticket.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer()
            
            # Send closing message
            embed = discord.Embed(
                title="🔒 Ticket Closing",
                description=f"This ticket is being closed by {interaction.user.mention}.",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="⏳",
                value="This channel will be deleted in 5 seconds.",
                inline=False
            )
            await channel.send(embed=embed)
            
            # Log the ticket
            logs_channel = discord.utils.get(interaction.guild.text_channels, name="ticket-logs")
            if logs_channel:
                log_embed = discord.Embed(
                    title="📋 Ticket Closed",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                log_embed.add_field(
                    name="Ticket",
                    value=f"{channel.name}",
                    inline=True
                )
                log_embed.add_field(
                    name="Closed By",
                    value=interaction.user.mention,
                    inline=True
                )
                if ticket_info:
                    log_embed.add_field(
                        name="Created By",
                        value=f"<@{ticket_info['user_id']}>",
                        inline=True
                    )
                    log_embed.add_field(
                        name="Category",
                        value=ticket_info.get("category", "Unknown"),
                        inline=True
                    )
                    if ticket_info.get("claimed_by"):
                        log_embed.add_field(
                            name="Claimed By",
                            value=f"<@{ticket_info['claimed_by']}>",
                            inline=True
                        )
                await logs_channel.send(embed=log_embed)
            
            # Delete the channel
            ticket_data.close_ticket(channel_id)
            await asyncio.sleep(5)
            try:
                await channel.delete()
            except:
                pass
        
        # ==========================================
        # REQUEST CLOSURE
        # ==========================================
        elif custom_id.startswith("request_close_"):
            channel_id = int(custom_id.split("_")[2])
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
                return
            
            ticket_info = ticket_data.get_ticket(channel_id)
            if not ticket_info:
                await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
                return
            
            # Only ticket creator can request closure
            if int(ticket_info["user_id"]) != interaction.user.id:
                await interaction.response.send_message(
                    "❌ Only the ticket creator can request closure.",
                    ephemeral=True
                )
                return
            
            await interaction.response.send_message(
                "✅ Closure requested. A staff member will close this ticket.",
                ephemeral=True
            )
            
            await channel.send(
                f"⏳ {interaction.user.mention} has requested this ticket to be closed. "
                f"A staff member will close it."
            )

async def setup(bot):
    await bot.add_cog(Ticket(bot))