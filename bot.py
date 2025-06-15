import os
import asyncio
import sqlite3
import discord
from discord.ext import commands
from tabulate import tabulate

# Database initialization
# Allow configuring the database location with an environment variable so
# Docker volumes or custom paths can be used for persistence.
DB_PATH = os.getenv('DATABASE_PATH', 'duescord.db')

def init_db():
    # Ensure the directory for the database exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'CREATE TABLE IF NOT EXISTS members ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT,'
        'name TEXT NOT NULL,'
        'paid INTEGER NOT NULL,'
        'comment TEXT'
        ')'
    )
    conn.commit()
    conn.close()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Track users who have requested to clear the table but have not yet
# confirmed. Mapping of user ID to a task that removes the pending state
# after a timeout.
_pending_clears = {}


def _parse_bool(value: str):
    """Return True or False if value looks like a boolean, otherwise None."""
    v = value.lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n"}:
        return False
    return None


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command(name='register')
async def register(ctx, *, args: str):
    """Register a user with dues status and optional comment.

    Usage: !register <first> [last] <paid> [comment]
    """
    tokens = args.split()
    if len(tokens) < 2:
        await ctx.send("Usage: !register <first> [last] <paid> [comment]")
        return

    # Determine if the second or third token is the paid flag
    paid_token = None
    first = tokens[0]
    last = None
    comment_tokens = []
    if len(tokens) >= 3 and _parse_bool(tokens[2]) is not None:
        last = tokens[1]
        paid_token = tokens[2]
        comment_tokens = tokens[3:]
    elif _parse_bool(tokens[1]) is not None:
        paid_token = tokens[1]
        comment_tokens = tokens[2:]
    else:
        await ctx.send("Usage: !register <first> [last] <paid> [comment]")
        return

    paid_val = _parse_bool(paid_token)
    if paid_val is None:
        await ctx.send("Paid value must be true or false")
        return

    name = first + (" " + last if last else "")
    comment = " ".join(comment_tokens) if comment_tokens else None

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO members (name, paid, comment) VALUES (?, ?, ?)',
        (name, int(paid_val), comment)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Registered {name} with paid={paid_val}.")

@bot.command(name='members')
async def members(ctx):
    """List all registered members in a table."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name, paid, COALESCE(comment, "") FROM members')
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send('No members found.')
        return

    table = tabulate(rows, headers=['Name', 'Paid', 'Comment'], tablefmt='pretty')
    await ctx.send(f"```\n{table}\n```")


@bot.command(name='clear_table')
async def clear_table(ctx, confirm: str = None):
    """Delete all members after a second confirmation."""
    user_id = ctx.author.id

    if confirm != 'confirm':
        # First step: ask for confirmation
        if user_id in _pending_clears:
            _pending_clears[user_id].cancel()
        async def timeout():
            await asyncio.sleep(30)
            _pending_clears.pop(user_id, None)
        task = asyncio.create_task(timeout())
        _pending_clears[user_id] = task
        await ctx.send('This will remove **all** members. Run `!clear_table confirm` within 30 seconds to proceed.')
        return

    task = _pending_clears.pop(user_id, None)
    if task is None:
        await ctx.send('Please run `!clear_table` first to confirm.')
        return
    task.cancel()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM members')
    conn.commit()
    conn.close()
    await ctx.send('All members have been removed.')

if __name__ == '__main__':
    init_db()
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('DISCORD_TOKEN environment variable not set.')
    else:
        bot.run(TOKEN)
