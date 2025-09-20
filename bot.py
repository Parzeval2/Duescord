import os
import asyncio
import sqlite3
from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
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
    c.execute(
        'CREATE TABLE IF NOT EXISTS tasks ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT,'
        'description TEXT NOT NULL,'
        'assignee_id INTEGER NOT NULL,'
        'created_by INTEGER,'
        'created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
        'completed INTEGER NOT NULL DEFAULT 0,'
        'completed_at TEXT'
        ')'
    )
    c.execute(
        'CREATE TABLE IF NOT EXISTS settings ('
        'key TEXT PRIMARY KEY,'
        'value TEXT NOT NULL'
        ')'
    )
    conn.commit()
    conn.close()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

CENTRAL_TZ = ZoneInfo('America/Chicago')

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


def _get_active_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, description, assignee_id FROM tasks '
        'WHERE completed = 0 ORDER BY created_at, id'
    )
    rows = c.fetchall()
    conn.close()
    return rows


def _format_task_table(tasks):
    formatted = [
        (task_id, description, f'<@{assignee_id}>')
        for task_id, description, assignee_id in tasks
    ]
    return tabulate(formatted, headers=['ID', 'Description', 'Assignee'], tablefmt='pretty')


def _get_task_channel_id():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', ('task_channel_id',))
    row = c.fetchone()
    conn.close()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _set_task_channel_id(channel_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        ('task_channel_id', str(channel_id)),
    )
    conn.commit()
    conn.close()


async def _send_active_tasks(destination):
    tasks = _get_active_tasks()
    if not tasks:
        await destination.send('There are no active tasks.')
        return
    table = _format_task_table(tasks)
    await destination.send(f"**Active Tasks**\n```\n{table}\n```")


@tasks.loop(time=time(hour=9, tzinfo=CENTRAL_TZ))
async def daily_task_digest():
    channel_id = _get_task_channel_id()
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return
    await _send_active_tasks(channel)


@daily_task_digest.before_loop
async def before_daily_task_digest():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    if not daily_task_digest.is_running():
        daily_task_digest.start()


@bot.command(name='task')
async def create_task(ctx, member: discord.Member, *, description: str):
    """Create a task assigned to a member."""
    description = description.strip()
    if not description:
        await ctx.send('Task description cannot be empty.')
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO tasks (description, assignee_id, created_by, created_at) '
        'VALUES (?, ?, ?, ?)',
        (description, member.id, ctx.author.id, datetime.utcnow().isoformat()),
    )
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    await ctx.send(f'Task {task_id} created for {member.mention}.')


@create_task.error
async def create_task_error(ctx, error):
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send('Please mention a valid member and provide a description. Usage: `!task @member <description>`')
    else:
        raise error


@bot.command(name='tasks')
async def list_tasks(ctx):
    """List all active tasks."""
    await _send_active_tasks(ctx)


@bot.command(name='complete', aliases=['complete_task'])
async def complete(ctx, task_id: int):
    """Mark a task as completed."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE tasks SET completed = 1, completed_at = CURRENT_TIMESTAMP '
        'WHERE id = ? AND completed = 0',
        (task_id,),
    )
    conn.commit()
    updated = c.rowcount
    conn.close()
    if updated:
        await ctx.send(f'Task {task_id} marked as complete.')
    else:
        await ctx.send('Active task not found with that ID.')


@complete.error
async def complete_error(ctx, error):
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send('Please provide the numeric ID of the task to complete. Usage: `!complete <id>`')
    else:
        raise error


@bot.command(name='reopen', aliases=['reopen_task'])
async def reopen(ctx, task_id: int):
    """Reopen a completed task."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE tasks SET completed = 0, completed_at = NULL '
        'WHERE id = ? AND completed = 1',
        (task_id,),
    )
    conn.commit()
    updated = c.rowcount
    conn.close()
    if updated:
        await ctx.send(f'Task {task_id} reopened.')
    else:
        await ctx.send('Completed task not found with that ID.')


@reopen.error
async def reopen_error(ctx, error):
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send('Please provide the numeric ID of the task to reopen. Usage: `!reopen <id>`')
    else:
        raise error


@bot.command(name='taskchannel', aliases=['set_task_channel'])
@commands.has_permissions(manage_guild=True)
async def taskchannel(ctx, channel: discord.TextChannel = None):
    """Set the channel where daily task digests are posted."""
    channel = channel or ctx.channel
    _set_task_channel_id(channel.id)
    await ctx.send(f'Daily task summaries will post in {channel.mention}.')


@taskchannel.error
async def taskchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You need the Manage Server permission to set the task channel.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Please mention a valid text channel.')
    else:
        raise error

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
    # Prevent duplicate names (case-insensitive)
    c.execute('SELECT id FROM members WHERE lower(name) = lower(?)', (name,))
    existing = c.fetchall()
    if existing:
        ids = ', '.join(str(r[0]) for r in existing)
        await ctx.send(f"{name} is already registered with id(s): {ids}. Use !update or !delete if needed.")
        conn.close()
        return

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
    c.execute('SELECT id, name, paid, COALESCE(comment, "") FROM members')
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.send('No members found.')
        return

    table = tabulate(rows, headers=['ID', 'Name', 'Paid', 'Comment'], tablefmt='pretty')
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


@bot.command(name='delete')
async def delete_member(ctx, member_id: int):
    """Remove a single member by their ID."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM members WHERE id = ?', (member_id,))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    if deleted:
        await ctx.send(f'Member {member_id} removed.')
    else:
        await ctx.send('Member not found.')


@bot.command(name='update')
async def update_member(ctx, member_id: int, paid: str, *, comment: str = None):
    """Update a member's paid status and optional comment."""
    paid_val = _parse_bool(paid)
    if paid_val is None:
        await ctx.send('Paid value must be true or false')
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if comment is None:
        c.execute('UPDATE members SET paid = ? WHERE id = ?', (int(paid_val), member_id))
    else:
        c.execute('UPDATE members SET paid = ?, comment = ? WHERE id = ?', (int(paid_val), comment, member_id))
    conn.commit()
    updated = c.rowcount
    conn.close()
    if updated:
        await ctx.send(f'Member {member_id} updated.')
    else:
        await ctx.send('Member not found.')


@bot.command(name='find')
async def find_member(ctx, *, query: str):
    """Search for members by name or comment."""
    like = f'%{query}%'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT id, name, paid, COALESCE(comment, "") FROM members '
        'WHERE name LIKE ? OR comment LIKE ?',
        (like, like)
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        await ctx.send('No matching members found.')
        return
    table = tabulate(rows, headers=['ID', 'Name', 'Paid', 'Comment'], tablefmt='pretty')
    await ctx.send(f"```\n{table}\n```")


@bot.command(name='unpaid')
async def unpaid_members(ctx):
    """List only members who have not paid."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, COALESCE(comment, "") FROM members WHERE paid = 0')
    rows = c.fetchall()
    conn.close()
    if not rows:
        await ctx.send('No unpaid members found.')
        return
    table = tabulate(rows, headers=['ID', 'Name', 'Comment'], tablefmt='pretty')
    await ctx.send(f"```\n{table}\n```")


@bot.command(name='stats')
async def stats(ctx):
    """Show counts of paid and unpaid members."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM members')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM members WHERE paid = 1')
    paid = c.fetchone()[0]
    unpaid = total - paid
    conn.close()
    await ctx.send(f'Total: {total}\nPaid: {paid}\nUnpaid: {unpaid}')


@bot.command(name='unpay_all')
async def unpay_all(ctx):
    """Mark all members as unpaid."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE members SET paid = 0')
    conn.commit()
    updated = c.rowcount
    conn.close()
    await ctx.send(f'Updated {updated} members to unpaid.')


@bot.command(name='help')
async def help_command(ctx):
    """Show all commands and their usage."""
    help_text = (
        "!task @member <description> - Create a task for a member\n"
        "!tasks - List active tasks\n"
        "!complete <id> (alias: !complete_task) - Mark a task complete\n"
        "!reopen <id> (alias: !reopen_task) - Reopen a completed task\n"
        "!taskchannel [#channel] (alias: !set_task_channel) - Configure the daily task summary channel\n"
        "!register <first> [last] <paid> [comment] - Register a member\n"
        "!members - List all registered members\n"
        "!clear_table [confirm] - Remove all members\n"
        "!delete <id> - Remove a member\n"
        "!update <id> <paid> [comment] - Update a member\n"
        "!find <query> - Search for members\n"
        "!unpaid - List unpaid members\n"
        "!stats - Show member statistics\n"
        "!unpay_all - Mark all members as unpaid\n"
        "!help - Show this message"
    )
    await ctx.send(help_text)

if __name__ == '__main__':
    init_db()
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('DISCORD_TOKEN environment variable not set.')
    else:
        bot.run(TOKEN)
