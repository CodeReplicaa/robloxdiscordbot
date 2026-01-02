import discord
from discord import app_commands
from discord.ext import commands, tasks
import requests
import asyncio
from datetime import datetime

# ---------- Hardcoded Tokens & API Keys ----------
# Only for testing/deployment on old Deta CLI
TOKEN = "MTQ1NTAxNTExNjI5Nzk5ODQ2OA.Gj_aVF.S2QkYxQyi4lFD4cEuXqIvM26job9CjQEvWDAlA"
PUSHOVER_TOKEN = "av92v7rp6duv41cwis3u8ujgvgag6n"
PUSHOVER_USER = "u5jt5qw5g7kweb8ifyi28t9x3r3da6"

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set")

# ---------- Roblox APIs ----------
PRESENCE_API = "https://presence.roblox.com/v1/presence/users"
USER_API = "https://users.roblox.com/v1/users/{}"
HEADSHOT_API = "https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={}&size=150x150&format=Png&isCircular=true"
PLACE_API = "https://games.roblox.com/v1/games/multiget-place-details?placeIds={}"

FRIENDS_COUNT_API = "https://friends.roblox.com/v1/users/{}/friends/count"
FOLLOWERS_COUNT_API = "https://friends.roblox.com/v1/users/{}/followers/count"
FOLLOWING_COUNT_API = "https://friends.roblox.com/v1/users/{}/followings/count"

STATUS_NAMES = {
    0: "Offline",
    1: "Online",
    2: "In Game",
    3: "In Studio"
}

# ---------- Bot Setup ----------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

# ---------- Tracking ----------
tracked_users = {}   # {user_id: channel}
last_status = {}     # {user_id: status}
notifications_enabled = True

# ---------- Pushover ----------
def send_ios_notification(title: str, message: str):
    if not notifications_enabled:
        return
    if not PUSHOVER_TOKEN or not PUSHOVER_USER:
        return
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "title": title,
                "message": message,
            },
            timeout=5
        )
    except Exception as e:
        print(f"Pushover error: {e}")

# ---------- Helper Functions ----------
def get_full_user_info(user_id: int):
    r = requests.get(USER_API.format(user_id))
    r.raise_for_status()
    data = r.json()
    created = datetime.strptime(data["created"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d")
    friends = requests.get(FRIENDS_COUNT_API.format(user_id)).json().get("count", 0)
    followers = requests.get(FOLLOWERS_COUNT_API.format(user_id)).json().get("count", 0)
    following = requests.get(FOLLOWING_COUNT_API.format(user_id)).json().get("count", 0)
    return {
        "username": data["name"],
        "display_name": data["displayName"],
        "created": created,
        "friends": friends,
        "followers": followers,
        "following": following
    }

def get_headshot(user_id: int):
    r = requests.get(HEADSHOT_API.format(user_id))
    r.raise_for_status()
    return r.json()["data"][0]["imageUrl"]

def get_presence(user_id: int):
    r = requests.post(PRESENCE_API, json={"userIds": [user_id]})
    r.raise_for_status()
    return r.json()["userPresences"][0]

def get_game_name(place_id):
    if not place_id:
        return None
    r = requests.get(PLACE_API.format(place_id))
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0]["name"] if data else None

async def send_user_status_embed(user_id: int, channel, only_on_change=False):
    try:
        presence = get_presence(user_id)
        status = presence.get("userPresenceType", 0)
        place_id = presence.get("placeId")
        previous_status = last_status.get(user_id)
        if only_on_change and previous_status == status:
            return
        last_status[user_id] = status
        info = get_full_user_info(user_id)
        headshot = get_headshot(user_id)
        if previous_status is not None and previous_status != status:
            send_ios_notification(
                "Roblox Status Update",
                f"{info['username']} is now {STATUS_NAMES[status]}"
            )
        embed = discord.Embed(
            title=f"{info['username']} | {info['display_name']}",
            description=(
                f"**Friends:** {info['friends']}\n"
                f"**Followers:** {info['followers']}\n"
                f"**Following:** {info['following']}\n"
                f"**Account Created:** {info['created']}\n"
                f"**Status:** {STATUS_NAMES[status]}"
            ),
            color=0x00ff00 if status != 0 else 0xff0000
        )
        if status == 2:
            game_name = get_game_name(place_id) or "Unknown Game"
            embed.add_field(name="Current Game", value=game_name, inline=False)
        embed.add_field(
            name="Rolimons",
            value=f"https://www.rolimons.com/player/{user_id}",
            inline=False
        )
        embed.set_thumbnail(url=headshot)
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Error for {user_id}: {e}")

# ---------- Events ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    presence_task.start()

@tasks.loop(seconds=15)
async def presence_task():
    for uid, channel in tracked_users.items():
        await send_user_status_embed(uid, channel, only_on_change=True)

# ---------- Slash Commands ----------
@bot.tree.command(name="track", description="Track a Roblox user by user ID")
async def track(interaction: discord.Interaction, user_id: int):
    tracked_users[user_id] = interaction.channel
    last_status[user_id] = None
    await interaction.response.send_message(f"Now tracking **{user_id}**")

@bot.tree.command(name="untrack", description="Untrack a Roblox user or all users")
async def untrack(interaction: discord.Interaction, user_id_or_all: str):
    if user_id_or_all.lower() == "all":
        tracked_users.clear()
        last_status.clear()
        await interaction.response.send_message("Stopped tracking all users.")
    else:
        user_id = int(user_id_or_all)
        tracked_users.pop(user_id, None)
        last_status.pop(user_id, None)
        await interaction.response.send_message(f"Stopped tracking **{user_id}**")

@bot.tree.command(name="list", description="List tracked Roblox users")
async def list_users(interaction: discord.Interaction):
    if not tracked_users:
        await interaction.response.send_message("No users are being tracked.")
        return
    msg = "\n".join(str(uid) for uid in tracked_users)
    await interaction.response.send_message(msg)

@bot.tree.command(name="notify", description="Enable or disable iOS notifications")
@app_commands.describe(state="on or off")
async def notify(interaction: discord.Interaction, state: str):
    global notifications_enabled
    if state.lower() == "on":
        notifications_enabled = True
        await interaction.response.send_message("📲 iOS notifications **ENABLED**")
    elif state.lower() == "off":
        notifications_enabled = False
        await interaction.response.send_message("🔕 iOS notifications **DISABLED**")
    else:
        await interaction.response.send_message("Usage: `/notify on` or `/notify off`")

# ---------- Run ----------
bot.run(TOKEN)
