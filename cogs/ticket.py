import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import asyncio
import secrets
import string
from datetime import datetime, timedelta

# ============================================
# GLOBAL CONFIGURATION
# ============================================
NOTIFICATION_CHANNEL_ID = 1527982333834166333  # Your specified channel ID

# ============================================
# 1. MODAL: Edit Ticket Name
# ============================================
class TicketNameModal(Modal, title="Edit Ticket Name"):
    new_name = TextInput(
        label="New Channel Name",
        placeholder="ticket-support-001",
        required=True,
        min_length=1,
        max_length=100
    )

    def __init__(self, ticket_channel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            await self.ticket_channel.edit(name=self.new_name.value)
            await interaction.followup.send(f"✅ Ticket channel renamed to: `{self.new_name.value}`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to rename: {e}", ephemeral=True)

# ============================================
# 2. MODAL: Change Category
# ============================================
class TicketCategoryModal(Modal, title="Move Ticket to Category"):
    category_name = TextInput(
        label="Category Name",
        placeholder="Support, Appeals, Reports...",
        required=True
    )

    def __init__(self, ticket_channel, guild):
        super().__init__()
        self.ticket_channel = ticket_channel
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        category = discord.utils.get(self.guild.categories, name=self.category_name.value)
        if not category:
            await interaction.followup.send(f"❌ Category `{self.category_name.value}` not found. Please use the exact name.", ephemeral=True)
            return
        
        try:
            await self.ticket_channel.edit(category=category)
            await interaction.followup.send(f"✅ Ticket moved to category: `{category.name}`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to move ticket: {e}", ephemeral=True)

# ============================================
# 3. MODAL: Edit Access (Add/Remove User)
# ============================================
class TicketAccessModal(Modal, title="Manage Ticket Access"):
    user_id = TextInput(
        label="User ID",
        placeholder="123456789012345678",
        required=True
    )
    action = TextInput(
        label="Action (add / remove)",
        placeholder="add or remove",
        required=True
    )

    def __init__(self, ticket_channel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            user = await interaction.guild.fetch_member(int(self.user_id.value))
            if not user:
                await interaction.followup.send("❌ Could not find a user with that ID.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Invalid User ID format.", ephemeral=True)
            return

        action = self.action.value.lower()
        if action not in ["add", "remove"]:
            await interaction.followup.send("❌ Action must be 'add' or 'remove'.", ephemeral=True)
            return

        try:
            overwrites = self.ticket_channel.overwrites_for(user)
            if action == "add":
                overwrites.read_messages = True
                overwrites.send_messages = True
                await self.ticket_channel.set_permissions(user, overwrite=overwrites)
                await interaction.followup.send(f"✅ {user.mention} has been added to the ticket.", ephemeral=True)
            else:
                await self.ticket_channel.set_permissions(user, overwrite=None)
                await interaction.followup.send(f"✅ {user.mention} has been removed from the ticket.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to update access: {e}", ephemeral=True)

# ============================================
# 4. MAIN TICKET CONTROL VIEW (PERSISTENT)
# ============================================
class TicketControlView(View):
    def __init__(self, log_channel: discord.TextChannel = None, support_roles=None):
        super().__init__(timeout=None)
        self.log_channel = log_channel
        self.support_roles = support_roles or []

    def is_staff_or_owner(self, interaction: discord.Interaction):
        has_role = any(role in interaction.user.roles for role in self.support_roles)
        is_owner = interaction.user.id == interaction.guild.owner_id
        return is_owner or has_role

    @discord.ui.button(label="Claim", emoji="👋", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        
        if not self.is_staff_or_owner(interaction):
            await interaction.followup.send("❌ You do not have permission to claim tickets. Only Staff/Owner can claim.", ephemeral=True)
            return

        try:
            async for entry in interaction.channel.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                if entry.target.id == interaction.channel.id:
                    opener = entry.user
                    if interaction.user.id == opener.id:
                        await interaction.followup.send("❌ You cannot claim your own ticket!", ephemeral=True)
                        return
                    break
        except:
            pass

        try:
            await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
            await interaction.followup.send(f"👋 {interaction.user.mention} has claimed this ticket.", ephemeral=False)
            
            if self.log_channel:
                claim_embed = discord.Embed(
                    title="👋 Ticket Claimed",
                    description=f"**Staff:** {interaction.user.mention}\n**Channel:** {interaction.channel.mention}",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                await self.log_channel.send(embed=claim_embed)
                
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to claim: {e}", ephemeral=True)

    @discord.ui.button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if not self.is_staff_or_owner(interaction):
            await interaction.followup.send("❌ Only Staff/Owner can close this ticket.", ephemeral=True)
            return
            
        await interaction.followup.send("🗑️ Closing ticket and deleting channel in 5 seconds...", ephemeral=False)
        
        if self.log_channel:
            close_embed = discord.Embed(
                title="🗑️ Ticket Closed",
                description=f"**Closed By:** {interaction.user.mention}\n**Channel:** {interaction.channel.mention}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await self.log_channel.send(embed=close_embed)
            
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Change Category", emoji="📂", style=discord.ButtonStyle.secondary, custom_id="ticket_category")
    async def change_category(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction):
            await interaction.response.send_message("❌ Only Staff/Owner can change the category.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketCategoryModal(interaction.channel, interaction.guild))

    @discord.ui.button(label="Edit Name", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="ticket_name")
    async def edit_name(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction):
            await interaction.response.send_message("❌ Only Staff/Owner can edit the channel name.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketNameModal(interaction.channel))

    @discord.ui.button(label="Edit Access", emoji="👤", style=discord.ButtonStyle.secondary, custom_id="ticket_access")
    async def edit_access(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction):
            await interaction.response.send_message("❌ Only Staff/Owner can manage ticket access.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketAccessModal(interaction.channel))

    @discord.ui.button(label="Request Closure", emoji="💬", style=discord.ButtonStyle.secondary, custom_id="ticket_request_close")
    async def request_closure(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction):
            await interaction.response.send_message("❌ Only Staff/Owner can request closure.", ephemeral=True)
            return
            
        await interaction.response.defer()
        await interaction.followup.send(
            f"⏰ {interaction.user.mention} has requested to close this ticket. It will auto-delete in **24 hours**.\n"
            f"Use `/cancelclose` inside this channel to prevent deletion.",
            ephemeral=False
        )

        async def auto_close_request():
            await asyncio.sleep(86400)
            try:
                if interaction.channel and interaction.channel.guild:
                    await interaction.channel.send("🔒 Auto-closing ticket after 24 hour request.")
                    await asyncio.sleep(5)
                    await interaction.channel.delete()
            except:
                pass
        
        asyncio.create_task(auto_close_request())

# ============================================
# 5. MODAL: OPEN TICKET (PROMPT)
# ============================================
class OpenTicketModal(Modal, title="Open a Ticket"):
    reason = TextInput(
        label="Reason for ticket",
        style=discord.TextStyle.paragraph,
        placeholder="Explain your issue in detail...",
        required=True,
        min_length=10
    )

    def __init__(self, support_roles, log_channel):
        super().__init__()
        self.support_roles = support_roles
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Check for existing ticket
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                if interaction.user in channel.members:
                    await interaction.followup.send("❌ You already have an open ticket!", ephemeral=True)
                    return

        # 2. Generate Ticket Code
        alphabet = string.ascii_lowercase + string.digits
        while True:
            ticket_code = ''.join(secrets.choice(alphabet) for _ in range(5))
            if not discord.utils.get(interaction.guild.channels, name=f"ticket-{ticket_code}"):
                break

        # 3. Find or Create a PRIVATE CATEGORY for the user
        category_name = f"tickets-{interaction.user.name}"
        user_category = discord.utils.get(interaction.guild.categories, name=category_name)

        if not user_category:
            # Create a hidden category visible only to the user, bot, owner, and staff
            category_overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True),
                interaction.guild.owner: discord.PermissionOverwrite(read_messages=True) # Owner sees ALL private categories
            }
            for role in self.support_roles:
                category_overwrites[role] = discord.PermissionOverwrite(read_messages=True)

            user_category = await interaction.guild.create_category(
                name=category_name,
                overwrites=category_overwrites,
                reason=f"Private category created for {interaction.user}"
            )

        # 4. Create Channel inside the Private Category
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            interaction.guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        for role in self.support_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_code}",
            category=user_category, # Put the ticket in their private category!
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user} for {self.reason.value}"
        )

        # --- NOTIFICATION: Ticket Created ---
        if self.log_channel:
            log_embed = discord.Embed(title="🎫 Ticket Opened", color=discord.Color.green(), timestamp=datetime.utcnow())
            log_embed.add_field(name="User", value=interaction.user.mention)
            log_embed.add_field(name="Reason", value=self.reason.value)
            log_embed.add_field(name="Category", value=user_category.name)
            log_embed.add_field(name="Channel", value=ticket_channel.mention)
            await self.log_channel.send(embed=log_embed)

        embed = discord.Embed(
            title=f"Ticket | {ticket_code}",
            description=f"Opened by {interaction.user.mention}\n**Reason:** {self.reason.value}\n\nPlease wait for a staff member to help you.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Use the buttons below to manage this ticket.")

        await ticket_channel.send(embed=embed, view=TicketControlView(self.log_channel, self.support_roles))
        await interaction.followup.send(f"✅ Ticket created! Please go to {ticket_channel.mention}", ephemeral=True)

# ============================================
# 6. OPEN TICKET BUTTON (ON PANEL)
# ============================================
class OpenTicketButton(discord.ui.Button):
    def __init__(self, support_roles, log_channel):
        super().__init__(style=discord.ButtonStyle.success, label="Open Ticket", emoji="🎫", custom_id="open_ticket_panel")
        self.support_roles = support_roles
        self.log_channel = log_channel

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OpenTicketModal(self.support_roles, self.log_channel))

# ============================================
# 7. PANEL VIEW (TO DEPLOY THE BUTTON)
# ============================================
class TicketPanelView(discord.ui.View):
    def __init__(self, support_roles, log_channel):
        super().__init__(timeout=None)
        self.add_item(OpenTicketButton(support_roles, log_channel))

# ============================================
# 8. THE MAIN COG
# ============================================
class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.panel_messages = {} 

    @commands.command(name="ticketsetup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx):
        """[Admin] Deploys the new Ticket Panel."""
        
        notification_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification_channel:
            await ctx.send(f"❌ Could not find the notification channel with ID `{NOTIFICATION_CHANNEL_ID}`.")
            return

        support_role = discord.utils.get(ctx.guild.roles, name="Support Team")
        if not support_role:
            support_role = await ctx.guild.create_role(name="Support Team", color=discord.Color.blue())

        embed = discord.Embed(
            title="Support Tickets",
            description="Click the button below to open a new ticket. Please describe your issue clearly!",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Our team will assist you as soon as possible.")

        view = TicketPanelView([support_role], notification_channel)
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()

    @commands.command(name="cancelclose")
    async def cancel_closure(self, ctx):
        await ctx.send("✅ Closure request cancelled. This ticket will remain open.")

async def setup(bot):
    await bot.add_cog(Ticket(bot))
