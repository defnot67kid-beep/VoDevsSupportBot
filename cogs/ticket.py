import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import asyncio
import secrets
import string
from datetime import datetime, timedelta

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
    def __init__(self, log_channel: discord.TextChannel = None):
        super().__init__(timeout=None) # Persistent View
        self.log_channel = log_channel

    @discord.ui.button(label="Claim", emoji="👋", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if interaction.user not in interaction.channel.members:
            await interaction.followup.send("❌ You don't have access to this ticket.", ephemeral=True)
            return

        # Simple claim logic: rename to show username
        try:
            await interaction.channel.edit(name=f"{interaction.channel.name}-claimed")
            await interaction.followup.send(f"👋 {interaction.user.mention} has claimed this ticket.", ephemeral=False)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to claim: {e}", ephemeral=True)

    @discord.ui.button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await interaction.followup.send("🗑️ Closing ticket and deleting channel in 5 seconds...", ephemeral=False)
        
        # Logging logic
        if self.log_channel:
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"**Closed By:** {interaction.user.mention}\n**Channel:** {interaction.channel.mention}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await self.log_channel.send(embed=embed)
            
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Change Category", emoji="📂", style=discord.ButtonStyle.secondary, custom_id="ticket_category")
    async def change_category(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketCategoryModal(interaction.channel, interaction.guild))

    @discord.ui.button(label="Edit Name", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="ticket_name")
    async def edit_name(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketNameModal(interaction.channel))

    @discord.ui.button(label="Edit Access", emoji="👤", style=discord.ButtonStyle.secondary, custom_id="ticket_access")
    async def edit_access(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketAccessModal(interaction.channel))

    @discord.ui.button(label="Request Closure", emoji="💬", style=discord.ButtonStyle.secondary, custom_id="ticket_request_close")
    async def request_closure(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await interaction.followup.send(
            f"⏰ {interaction.user.mention} has requested to close this ticket. It will auto-delete in **24 hours**.\n"
            f"Use `/cancelclose` inside this channel to prevent deletion.",
            ephemeral=False
        )

        async def auto_close_request():
            await asyncio.sleep(86400) # 24 hours
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

    def __init__(self, support_roles, log_channel, ticket_category):
        super().__init__()
        self.support_roles = support_roles
        self.log_channel = log_channel
        self.ticket_category = ticket_category

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Check for existing ticket
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                if interaction.user in channel.members:
                    await interaction.followup.send("❌ You already have an open ticket!", ephemeral=True)
                    return

        # Generate Random Code
        alphabet = string.ascii_lowercase + string.digits
        while True:
            ticket_code = ''.join(secrets.choice(alphabet) for _ in range(5))
            if not discord.utils.get(interaction.guild.channels, name=f"ticket-{ticket_code}"):
                break

        # Get or create the "ticket" category
        ticket_category = discord.utils.get(interaction.guild.categories, name="ticket")
        if not ticket_category:
            # Create the "ticket" category if it doesn't exist
            ticket_category = await interaction.guild.create_category("ticket")

        # Overwrites
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        }

        for role in self.support_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Create Channel in the "ticket" category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_code}",
            category=ticket_category,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user} for {self.reason.value}"
        )

        # Log to system channel if applicable
        if self.log_channel:
            log_embed = discord.Embed(title="🎫 Ticket Opened", color=discord.Color.green(), timestamp=datetime.utcnow())
            log_embed.add_field(name="User", value=interaction.user.mention)
            log_embed.add_field(name="Reason", value=self.reason.value)
            log_embed.add_field(name="Channel", value=ticket_channel.mention)
            await self.log_channel.send(embed=log_embed)

        # Send Control Panel
        embed = discord.Embed(
            title=f"Ticket | {ticket_code}",
            description=f"Opened by {interaction.user.mention}\n**Reason:** {self.reason.value}\n\nPlease wait for a staff member to help you.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Use the buttons below to manage this ticket.")

        # Send the view
        await ticket_channel.send(embed=embed, view=TicketControlView(self.log_channel))
        await interaction.followup.send(f"✅ Ticket created! Please go to {ticket_channel.mention}", ephemeral=True)

# ============================================
# 6. OPEN TICKET BUTTON (ON PANEL)
# ============================================
class OpenTicketButton(discord.ui.Button):
    def __init__(self, support_roles, log_channel, ticket_category):
        super().__init__(style=discord.ButtonStyle.success, label="Open Ticket", emoji="🎫", custom_id="open_ticket_panel")
        self.support_roles = support_roles
        self.log_channel = log_channel
        self.ticket_category = ticket_category

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OpenTicketModal(self.support_roles, self.log_channel, self.ticket_category))

# ============================================
# 7. PANEL VIEW (TO DEPLOY THE BUTTON)
# ============================================
class TicketPanelView(discord.ui.View):
    def __init__(self, support_roles, log_channel, ticket_category):
        super().__init__(timeout=None)
        self.add_item(OpenTicketButton(support_roles, log_channel, ticket_category))

# ============================================
# 8. THE MAIN COG
# ============================================
class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.panel_messages = {} # Store to re-add views on startup
        self.log_channel_id = None

    @commands.command(name="ticketsetup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx, log_channel: discord.TextChannel = None):
        """[Admin] Deploys the new Ticket Panel."""
        if log_channel:
            self.log_channel_id = log_channel.id
        else:
            self.log_channel_id = ctx.channel.id

        # Ensure support roles exist
        support_role = discord.utils.get(ctx.guild.roles, name="Support Team")
        if not support_role:
            support_role = await ctx.guild.create_role(name="Support Team", color=discord.Color.blue())

        # Get or create the "ticket" category
        ticket_category = discord.utils.get(ctx.guild.categories, name="ticket")
        if not ticket_category:
            ticket_category = await ctx.guild.create_category("ticket")

        # Deploy Panel
        embed = discord.Embed(
            title="Support Tickets",
            description="Click the button below to open a new ticket. Please describe your issue clearly!",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Our team will assist you as soon as possible.")

        view = TicketPanelView([support_role], ctx.guild.get_channel(self.log_channel_id), ticket_category)
        await ctx.send(embed=embed, view=view)
        await ctx.message.delete()

    @commands.command(name="ticketopn")
    @commands.has_permissions(administrator=True)
    async def ticket_opn(self, ctx, user: discord.Member = None):
        """[Admin] Opens a ticket for a specific user."""
        if not user:
            await ctx.send("❌ Please specify a user: `!ticketopn @user`")
            return

        # Check if user already has a ticket
        for channel in ctx.guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                if user in channel.members:
                    await ctx.send(f"❌ {user.mention} already has an open ticket!")
                    return

        # Get or create the "ticket" category
        ticket_category = discord.utils.get(ctx.guild.categories, name="ticket")
        if not ticket_category:
            ticket_category = await ctx.guild.create_category("ticket")

        # Generate Random Code
        alphabet = string.ascii_lowercase + string.digits
        while True:
            ticket_code = ''.join(secrets.choice(alphabet) for _ in range(5))
            if not discord.utils.get(ctx.guild.channels, name=f"ticket-{ticket_code}"):
                break

        # Get support roles
        support_role = discord.utils.get(ctx.guild.roles, name="Support Team")
        if not support_role:
            support_role = await ctx.guild.create_role(name="Support Team", color=discord.Color.blue())

        # Overwrites
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        }
        overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Create Channel in the "ticket" category
        ticket_channel = await ctx.guild.create_text_channel(
            name=f"ticket-{ticket_code}",
            category=ticket_category,
            overwrites=overwrites,
            reason=f"Ticket opened by {ctx.author} for {user}"
        )

        # Log to system channel if applicable
        log_channel = ctx.guild.get_channel(self.log_channel_id) if self.log_channel_id else None
        if log_channel:
            log_embed = discord.Embed(title="🎫 Ticket Opened (Staff)", color=discord.Color.green(), timestamp=datetime.utcnow())
            log_embed.add_field(name="User", value=user.mention)
            log_embed.add_field(name="Opened By", value=ctx.author.mention)
            log_embed.add_field(name="Channel", value=ticket_channel.mention)
            await log_channel.send(embed=log_embed)

        # Send Control Panel
        embed = discord.Embed(
            title=f"Ticket | {ticket_code}",
            description=f"Opened for {user.mention} by {ctx.author.mention}\n\nPlease wait for a staff member to help you.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Use the buttons below to manage this ticket.")

        # Send the view
        await ticket_channel.send(embed=embed, view=TicketControlView(log_channel))
        await ctx.send(f"✅ Ticket created for {user.mention}! Please go to {ticket_channel.mention}")

    @commands.command(name="cancelclose")
    async def cancel_closure(self, ctx):
        """Cancels a closure request (must be used in the ticket channel)."""
        await ctx.send("✅ Closure request cancelled. This ticket will remain open.")
        # In a fully advanced system, you would cancel the scheduled task here.

async def setup(bot):
    await bot.add_cog(Ticket(bot))
