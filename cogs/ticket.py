import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import asyncio
import secrets
import string
from datetime import datetime

# ============================================
# GLOBAL CONFIGURATION
# ============================================
NOTIFICATION_CHANNEL_ID = 1527982333834166333
TICKET_CATEGORY_ID = 1528040065714884798  # Hardcoded Category ID
BAD_WORDS = ["nigger", "nigga", "faggot", "retard", "kike", "chink"] 

# ============================================
# 1. MULTI-QUESTION OPEN TICKET MODAL
# ============================================
class OpenTicketModal(Modal, title="Appeals Ticket"):
    appeal_type = TextInput(
        label="What kind of appeal is this?",
        placeholder="Partnering, Ban Appeal, etc...",
        required=True,
        max_length=50
    )
    second_question = TextInput(
        label="Question 2", # Label will be updated dynamically
        placeholder="Answer here...",
        required=True,
        max_length=500
    )
    reason = TextInput(
        label="Explain your reason behind the appeal.",
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

        # --- FILTER: Check for racist / abusive language ---
        combined_text = f"{self.appeal_type.value} {self.second_question.value} {self.reason.value}"
        if any(bad_word in combined_text.lower() for bad_word in BAD_WORDS):
            await interaction.followup.send("❌ Your ticket reason contains inappropriate or hateful language. Please rephrase and try again.", ephemeral=True)
            return

        # 1. Get the hardcoded Category
        ticket_category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        if not ticket_category or not isinstance(ticket_category, discord.CategoryChannel):
            await interaction.followup.send("❌ The ticket category could not be found or is invalid. Please contact an administrator.", ephemeral=True)
            return

        # 2. Check for existing open ticket
        for channel in ticket_category.channels:
            if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                if interaction.user in channel.members:
                    await interaction.followup.send("❌ You already have an open ticket! Please check the ticket category.", ephemeral=True)
                    return

        # 3. Generate Ticket Code
        alphabet = string.ascii_lowercase + string.digits
        while True:
            ticket_code = ''.join(secrets.choice(alphabet) for _ in range(5))
            if not discord.utils.get(interaction.guild.channels, name=f"ticket-{ticket_code}"):
                break

        # 4. Create or Update Previous Ticket History in User's Nickname
        previous_tickets = []
        if interaction.user.nick:
            if "| Tickets: [" in interaction.user.nick:
                start = interaction.user.nick.find("[") + 1
                end = interaction.user.nick.find("]")
                if start != -1 and end != -1:
                    previous_tickets = interaction.user.nick[start:end].split(", ")
        
        previous_tickets.append(ticket_code)
        if len(previous_tickets) > 10:
            previous_tickets.pop(0)
            
        new_nick = interaction.user.display_name
        if not interaction.user.nick:
            new_nick = interaction.user.name
        else:
            new_nick = interaction.user.nick.split(" |")[0]
        new_nick += f" | Tickets: [{', '.join(previous_tickets)}]"
        
        try:
            await interaction.user.edit(nick=new_nick)
        except:
            pass

        # 5. PRIVATE PERMISSION SETUP (LOCKED TO STAFF ONLY)
        overwrites = {
            # Deny @everyone from seeing anything
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            # Allow the Bot
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            # Allow the Ticket Creator
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            # Allow the Owner
            interaction.guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # Grant access to ALL Support Roles
        for role in self.support_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 6. Create Ticket Channel inside the Hardcoded Category
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_code}",
            category=ticket_category,
            overwrites=overwrites,
            reason=f"Ticket opened by {interaction.user}"
        )
        await ticket_channel.edit(topic=f"Opened by: {interaction.user.id}")

        # 7. Auto-Assign Logic (IGNORES DND AND OFFLINE)
        assigned_staff = None
        
        active_staff_role = discord.utils.get(interaction.guild.roles, name="Active Staff")
        
        if active_staff_role:
            for member in active_staff_role.members:
                if member.id != interaction.user.id:
                    assigned_staff = member
                    break
        
        if not assigned_staff:
            for role in self.support_roles:
                for member in role.members:
                    if member.id != interaction.user.id:
                        if member.status not in [discord.Status.dnd, discord.Status.offline]:
                            assigned_staff = member
                            break
                if assigned_staff:
                    break

        # 8. CREATE THE COMBINED PINNED EMBED
        prev_tix_str = "\n".join([f"• {code} ( # *unknown* )" for code in previous_tickets]) if previous_tickets else "None"

        profile_text = f"**User:** {interaction.user.mention}\n**ID:** `{interaction.user.id}`\n**Joined Server:** <t:{int(interaction.user.joined_at.timestamp())}:R>\n**Joined Discord:** <t:{int(interaction.user.created_at.timestamp())}:R>"

        combined_description = (
            f"Ticket created by {interaction.user.mention} (`{interaction.user.id}`)\n\n"
            f"**Ticket Controls**\nUse the buttons below to manage this ticket.\n\n"
            f"**Vortex Discord Profile**\n{profile_text}\n\n"
            f"**Previous Tickets**\n{prev_tix_str}"
        )

        main_embed = discord.Embed(
            title=f"Appeals Ticket `{ticket_code}`",
            description=combined_description,
            color=discord.Color.dark_embed()
        )
        
        # --- DYNAMIC LABEL FOR EMBED ---
        is_partner = "partner" in self.appeal_type.value.lower()
        second_label = "What punishment did you receive?" if not is_partner else "Partnership Details"
        
        main_embed.add_field(name="What kind of appeal is this?", value=self.appeal_type.value, inline=False)
        main_embed.add_field(name=second_label, value=self.second_question.value, inline=False)
        main_embed.add_field(name="Explain your reason behind the appeal.", value=self.reason.value, inline=False)

        # 9. Construct Auto-Assign Message
        assign_msg = ""
        if assigned_staff:
            assign_msg = f"{assigned_staff.mention} has been assigned to this ticket automatically. Please note that your ticket may be assigned to someone else depending on what is needed to resolve your issue.\n\n**Do NOT ping this person, they have been notified already.**"
        else:
            assign_msg = "No online staff members are currently available. Please wait for a staff member to help you."

        # 10. Send Message and Pin it
        view = TicketControlView(self.log_channel, self.support_roles, ticket_code)
        sent_message = await ticket_channel.send(content=assign_msg, embed=main_embed, view=view)
        
        try:
            await sent_message.pin()
        except:
            pass

        # 11. Notification Log
        if self.log_channel:
            log_embed = discord.Embed(title="🎫 Ticket Opened", color=discord.Color.green(), timestamp=datetime.utcnow())
            log_embed.add_field(name="User", value=interaction.user.mention)
            log_embed.add_field(name="Reason", value=self.reason.value)
            log_embed.add_field(name="Channel", value=ticket_channel.mention)
            await self.log_channel.send(embed=log_embed)

        await interaction.followup.send(f"✅ Ticket created! Please go to {ticket_channel.mention}", ephemeral=True)

# ============================================
# 2. MODALS: Edit Name / Category / Access
# ============================================
class TicketNameModal(Modal, title="Edit Ticket Name"):
    new_name = TextInput(label="New Channel Name", placeholder="ticket-support-001", required=True)
    def __init__(self, ticket_channel): super().__init__(); self.ticket_channel = ticket_channel
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            await self.ticket_channel.edit(name=self.new_name.value)
            await interaction.followup.send(f"✅ Renamed to: `{self.new_name.value}`", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

class TicketCategoryModal(Modal, title="Move Ticket to Category"):
    category_name = TextInput(label="Category Name", placeholder="Support, Appeals...", required=True)
    def __init__(self, ticket_channel, guild): super().__init__(); self.ticket_channel = ticket_channel; self.guild = guild
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        category = discord.utils.get(self.guild.categories, name=self.category_name.value)
        if not category: await interaction.followup.send(f"❌ Category not found.", ephemeral=True); return
        try:
            await self.ticket_channel.edit(category=category)
            await interaction.followup.send(f"✅ Moved to: `{category.name}`", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

class TicketAccessModal(Modal, title="Manage Ticket Access"):
    user_id = TextInput(label="User ID", placeholder="123456789012345678", required=True)
    action = TextInput(label="Action (add / remove)", placeholder="add or remove", required=True)
    def __init__(self, ticket_channel): super().__init__(); self.ticket_channel = ticket_channel
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try: user = await interaction.guild.fetch_member(int(self.user_id.value))
        except: await interaction.followup.send("❌ Invalid ID.", ephemeral=True); return
        action = self.action.value.lower()
        if action not in ["add", "remove"]: await interaction.followup.send("❌ Use 'add' or 'remove'.", ephemeral=True); return
        try:
            if action == "add":
                await self.ticket_channel.set_permissions(user, read_messages=True, send_messages=True)
            else:
                await self.ticket_channel.set_permissions(user, overwrite=None)
            await interaction.followup.send(f"✅ {user.mention} {action}ed.", ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ============================================
# 3. TICKET CONTROL VIEW
# ============================================
class TicketControlView(View):
    def __init__(self, log_channel, support_roles, ticket_code):
        super().__init__(timeout=None)
        self.log_channel = log_channel
        self.support_roles = support_roles
        self.ticket_code = ticket_code

    def is_staff_or_owner(self, interaction):
        has_role = any(role in interaction.user.roles for role in self.support_roles)
        return has_role or interaction.user.id == interaction.guild.owner_id

    async def is_ticket_creator(self, interaction):
        try:
            async for entry in interaction.channel.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                if entry.target.id == interaction.channel.id: return interaction.user.id == entry.user.id
        except: pass
        return False

    @discord.ui.button(label="Claim", emoji="👋", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if not self.is_staff_or_owner(interaction): return await interaction.followup.send("❌ Staff/Owner only.", ephemeral=True)
        if await self.is_ticket_creator(interaction): return await interaction.followup.send("❌ Cannot claim own ticket.", ephemeral=True)
        try:
            new_name = interaction.channel.name.replace("ticket-", "claimed-", 1)
            await interaction.channel.edit(name=new_name)
            await interaction.followup.send(f"👋 {interaction.user.mention} has claimed this ticket.", ephemeral=False)
            if self.log_channel:
                embed = discord.Embed(title="👋 Ticket Claimed", description=f"**Staff:** {interaction.user.mention}\n**Code:** {self.ticket_code}", color=discord.Color.blue())
                await self.log_channel.send(embed=embed)
        except Exception as e: await interaction.followup.send(f"❌ Failed to claim: {e}", ephemeral=True)

    @discord.ui.button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        is_creator = await self.is_ticket_creator(interaction)
        if not (self.is_staff_or_owner(interaction) or is_creator): return await interaction.followup.send("❌ Staff/Owner/Creator only.", ephemeral=True)
        await interaction.followup.send("🗑️ Deleting in 5 seconds...", ephemeral=False)
        if self.log_channel:
            embed = discord.Embed(title="🗑️ Ticket Closed", description=f"**Closed By:** {interaction.user.mention}\n**Code:** {self.ticket_code}", color=discord.Color.red())
            await self.log_channel.send(embed=embed)
        await asyncio.sleep(5)
        try: await interaction.channel.delete()
        except: pass

    @discord.ui.button(label="Change Category", emoji="📂", style=discord.ButtonStyle.secondary, custom_id="ticket_category")
    async def change_cat(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction): return await interaction.response.send_message("❌ Staff/Owner only.", ephemeral=True)
        await interaction.response.send_modal(TicketCategoryModal(interaction.channel, interaction.guild))

    @discord.ui.button(label="Edit Name", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="ticket_name")
    async def edit_name(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction): return await interaction.response.send_message("❌ Staff/Owner only.", ephemeral=True)
        await interaction.response.send_modal(TicketNameModal(interaction.channel))

    @discord.ui.button(label="Edit Access", emoji="👤", style=discord.ButtonStyle.secondary, custom_id="ticket_access")
    async def edit_access(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff_or_owner(interaction): return await interaction.response.send_message("❌ Staff/Owner only.", ephemeral=True)
        await interaction.response.send_modal(TicketAccessModal(interaction.channel))

    @discord.ui.button(label="Request Closure", emoji="💬", style=discord.ButtonStyle.secondary, custom_id="ticket_request_close")
    async def request_close(self, interaction: discord.Interaction, button: Button):
        is_creator = await self.is_ticket_creator(interaction)
        if not (self.is_staff_or_owner(interaction) or is_creator): return await interaction.response.send_message("❌ Staff/Owner/Creator only.", ephemeral=True)
        await interaction.response.defer()
        await interaction.followup.send(f"⏰ {interaction.user.mention} requested closure. Auto-deletes in **24 hours**.", ephemeral=False)
        async def auto_close():
            await asyncio.sleep(86400)
            try:
                if interaction.channel and interaction.channel.guild:
                    await interaction.channel.send("🔒 Auto-closing.")
                    await asyncio.sleep(5)
                    await interaction.channel.delete()
            except: pass
        asyncio.create_task(auto_close())

# ============================================
# 4. ACTIVE STAFF AUTO-ROLE MANAGER
# ============================================
class StaffRoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not after.guild: return

        support_role = discord.utils.get(after.guild.roles, name="Support Team")
        if not support_role or support_role not in after.roles: return

        active_role = discord.utils.get(after.guild.roles, name="Active Staff")
        if not active_role:
            active_role = await after.guild.create_role(name="Active Staff", color=discord.Color.green())
            await active_role.edit(position=support_role.position - 1)

        if after.status in [discord.Status.offline, discord.Status.dnd]:
            if active_role in after.roles:
                await after.remove_roles(active_role, reason="Staff went offline or Do Not Disturb")
        elif after.status in [discord.Status.online, discord.Status.idle]:
            if active_role not in after.roles:
                await after.add_roles(active_role, reason="Staff came online")

# ============================================
# 5. OPEN TICKET BUTTON & PANEL VIEW
# ============================================
class OpenTicketButton(discord.ui.Button):
    def __init__(self, support_roles, log_channel):
        super().__init__(style=discord.ButtonStyle.success, label="Open Ticket", emoji="🎫", custom_id="open_ticket_panel")
        self.support_roles = support_roles
        self.log_channel = log_channel
    async def callback(self, interaction: discord.Interaction):
        # DYNAMIC MODAL LOGIC
        # We create the modal, but before sending it, we check the user's input
        modal = OpenTicketModal(self.support_roles, self.log_channel)
        
        # We have to hook into the on_submit. We can't dynamically change the label of a TextInput 
        # after the modal is shown, BUT we can change the placeholder to guide them.
        # To make it actually change the Label, we must use a custom approach.
        # For this code, we will let the User type freely and handle it in the embed.
        
        await interaction.response.send_modal(modal)

class TicketPanelView(discord.ui.View):
    def __init__(self, support_roles, log_channel):
        super().__init__(timeout=None)
        self.add_item(OpenTicketButton(support_roles, log_channel))

# ============================================
# 6. MAIN COG
# ============================================
class Ticket(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
        self.bot.add_cog(StaffRoleManager(bot))

    @commands.command(name="ticketsetup")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx):
        notification = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not notification: return await ctx.send(f"❌ Could not find notification channel.")
        role = discord.utils.get(ctx.guild.roles, name="Support Team")
        if not role: role = await ctx.guild.create_role(name="Support Team", color=discord.Color.blue())
        embed = discord.Embed(title="Support Tickets", description="Click the button below to open a new ticket.", color=discord.Color.blue())
        await ctx.send(embed=embed, view=TicketPanelView([role], notification))
        await ctx.message.delete()

async def setup(bot): await bot.add_cog(Ticket(bot))
