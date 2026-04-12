import os
import asyncio
import sqlite3
import threading
from functools import wraps
from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for
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

MODERATOR_ROLE_NAME = os.getenv('MODERATOR_ROLE_NAME', 'Moderator')
WEB_ENABLED = os.getenv('WEB_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'}
WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
WEB_PORT = int(os.getenv('WEB_PORT', '8080'))
WEB_ADMIN_TOKEN = os.getenv('WEB_ADMIN_TOKEN')
WEB_SECRET_KEY = os.getenv('WEB_SECRET_KEY', 'duescord-web-secret')

web_app = Flask(__name__)
web_app.secret_key = WEB_SECRET_KEY


def _fetch_rows(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _is_admin_logged_in():
    return bool(WEB_ADMIN_TOKEN and session.get('is_admin'))


def _admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _is_admin_logged_in():
            return jsonify({'error': 'Admin authentication required.'}), 403
        return func(*args, **kwargs)
    return wrapper


@web_app.route('/', methods=['GET'])
def web_index():
    members = _fetch_rows('SELECT id, name, paid, COALESCE(comment, "") AS comment FROM members ORDER BY id')
    tasks = _fetch_rows(
        'SELECT id, description, assignee_id, created_by, created_at, completed, completed_at '
        'FROM tasks ORDER BY created_at DESC, id DESC'
    )
    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Duescord Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 2rem; }
                .tabs { display: flex; gap: .5rem; margin-bottom: 1rem; }
                .tab-btn { padding: .5rem .75rem; border: 1px solid #aaa; cursor: pointer; background: #f4f4f4; }
                .tab-btn.active { background: #dce9ff; border-color: #4b74c6; }
                .tab-panel { display: none; }
                .tab-panel.active { display: block; }
                table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
                th, td { border: 1px solid #ddd; padding: .4rem; text-align: left; }
                th { background: #fafafa; }
                .meta { margin-bottom: 1rem; color: #444; }
                .actions { margin-bottom: .75rem; display: flex; gap: .5rem; align-items: center; }
                .notice { padding: .6rem; background: #fff7df; border: 1px solid #efcf73; border-radius: .25rem; }
            </style>
        </head>
        <body>
            <h1>Duescord Web Interface</h1>
            <div class="meta">
                Admin mode: <strong>{{ "Enabled" if admin_token_set else "Disabled (set WEB_ADMIN_TOKEN)" }}</strong>
                {% if admin_logged_in %}
                    | Logged in as admin (<a href="{{ url_for('admin_logout') }}">logout</a>)
                {% elif admin_token_set %}
                    | <a href="{{ url_for('admin_login') }}">admin login</a>
                {% endif %}
            </div>
            <div class="tabs">
                <button class="tab-btn active" data-tab="members">Members</button>
                <button class="tab-btn" data-tab="tasks">Tasks</button>
                <button class="tab-btn" data-tab="admin">Admin SQL Browser</button>
            </div>

            <section id="members" class="tab-panel active">
                <h2>Members</h2>
                <table>
                    <thead><tr><th>ID</th><th>Name</th><th>Paid</th><th>Comment</th></tr></thead>
                    <tbody>
                    {% for row in members %}
                        <tr><td>{{ row.id }}</td><td>{{ row.name }}</td><td>{{ row.paid }}</td><td>{{ row.comment }}</td></tr>
                    {% endfor %}
                    </tbody>
                </table>
            </section>

            <section id="tasks" class="tab-panel">
                <h2>Tasks</h2>
                <table>
                    <thead><tr><th>ID</th><th>Description</th><th>Assignee</th><th>Created By</th><th>Created At</th><th>Completed</th><th>Completed At</th></tr></thead>
                    <tbody>
                    {% for row in tasks %}
                        <tr>
                            <td>{{ row.id }}</td><td>{{ row.description }}</td><td>{{ row.assignee_id }}</td>
                            <td>{{ row.created_by }}</td><td>{{ row.created_at }}</td><td>{{ row.completed }}</td><td>{{ row.completed_at or "" }}</td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
            </section>

            <section id="admin" class="tab-panel">
                <h2>Admin SQL Browser</h2>
                {% if not admin_token_set %}
                    <div class="notice">Admin token not configured. Set <code>WEB_ADMIN_TOKEN</code> to enable this tab.</div>
                {% elif not admin_logged_in %}
                    <div class="notice">Please <a href="{{ url_for('admin_login') }}">login as admin</a> to browse SQL tables.</div>
                {% else %}
                    <div class="actions">
                        <label for="table-select">Table:</label>
                        <select id="table-select"></select>
                        <button id="refresh-table">Load</button>
                    </div>
                    <div id="admin-table"></div>
                {% endif %}
            </section>

            <script>
                document.querySelectorAll('.tab-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                        btn.classList.add('active');
                        document.getElementById(btn.dataset.tab).classList.add('active');
                    });
                });

                const tableSelect = document.getElementById('table-select');
                const refreshBtn = document.getElementById('refresh-table');
                const tableContainer = document.getElementById('admin-table');

                async function loadTableList() {
                    if (!tableSelect) return;
                    const response = await fetch('/api/admin/tables');
                    if (!response.ok) return;
                    const data = await response.json();
                    tableSelect.innerHTML = '';
                    data.tables.forEach(table => {
                        const option = document.createElement('option');
                        option.value = table;
                        option.textContent = table;
                        tableSelect.appendChild(option);
                    });
                    if (data.tables.length > 0) {
                        await loadTableData(data.tables[0]);
                    }
                }

                async function loadTableData(tableName) {
                    const response = await fetch(`/api/admin/table/${encodeURIComponent(tableName)}`);
                    if (!response.ok) {
                        tableContainer.innerHTML = '<div class="notice">Unable to load table data.</div>';
                        return;
                    }
                    const data = await response.json();
                    let html = '<table><thead><tr>';
                    data.columns.forEach(col => { html += `<th>${col}</th>`; });
                    html += '</tr></thead><tbody>';
                    data.rows.forEach(row => {
                        html += '<tr>';
                        data.columns.forEach(col => {
                            const value = row[col] ?? '';
                            html += `<td>${value}</td>`;
                        });
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                    tableContainer.innerHTML = html;
                }

                if (refreshBtn) {
                    refreshBtn.addEventListener('click', async () => {
                        if (tableSelect.value) await loadTableData(tableSelect.value);
                    });
                    tableSelect.addEventListener('change', async () => {
                        if (tableSelect.value) await loadTableData(tableSelect.value);
                    });
                    loadTableList();
                }
            </script>
        </body>
        </html>
        """,
        members=members,
        tasks=tasks,
        admin_token_set=bool(WEB_ADMIN_TOKEN),
        admin_logged_in=_is_admin_logged_in(),
    )


@web_app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if not WEB_ADMIN_TOKEN:
        return redirect(url_for('web_index'))
    error = None
    if request.method == 'POST':
        token = (request.form.get('token') or '').strip()
        if token == WEB_ADMIN_TOKEN:
            session['is_admin'] = True
            return redirect(url_for('web_index'))
        error = 'Invalid admin token.'
    return render_template_string(
        """
        <h1>Duescord Admin Login</h1>
        {% if error %}<p style="color: red;">{{ error }}</p>{% endif %}
        <form method="post">
            <label>Admin token: <input name="token" type="password" autofocus required></label>
            <button type="submit">Login</button>
        </form>
        <p><a href="{{ url_for('web_index') }}">Back to dashboard</a></p>
        """,
        error=error,
    )


@web_app.route('/admin/logout', methods=['GET'])
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('web_index'))


@web_app.route('/api/admin/tables', methods=['GET'])
@_admin_required
def api_admin_tables():
    rows = _fetch_rows(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return jsonify({'tables': [row['name'] for row in rows]})


@web_app.route('/api/admin/table/<table_name>', methods=['GET'])
@_admin_required
def api_admin_table_data(table_name):
    available_tables = {
        row['name']
        for row in _fetch_rows("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    }
    if table_name not in available_tables:
        return jsonify({'error': 'Unknown table.'}), 404
    column_rows = _fetch_rows(f'PRAGMA table_info("{table_name}")')
    columns = [row['name'] for row in column_rows]
    rows = _fetch_rows(f'SELECT * FROM "{table_name}" LIMIT 200')
    return jsonify({'table': table_name, 'columns': columns, 'rows': rows})


def _start_web_interface():
    if not WEB_ENABLED:
        print('Web interface disabled (set WEB_ENABLED=true to enable).')
        return
    thread = threading.Thread(
        target=lambda: web_app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()
    print(f'Web interface running on http://{WEB_HOST}:{WEB_PORT}')


def _has_named_role(member, role_name):
    return any(role.name == role_name for role in getattr(member, 'roles', []))


def moderator_only():
    async def predicate(ctx):
        if ctx.guild is None:
            raise commands.CheckFailure('This command can only be used in a server.')
        member = ctx.author
        if _has_named_role(member, MODERATOR_ROLE_NAME) or getattr(member.guild_permissions, 'administrator', False):
            return True
        raise commands.MissingRole(MODERATOR_ROLE_NAME)
    return commands.check(predicate)


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


async def _get_screen_name(assignee_id, guild):
    if guild is not None:
        member = guild.get_member(assignee_id)
        if member is not None:
            return member.display_name

    user = bot.get_user(assignee_id)
    if user is None:
        try:
            user = await bot.fetch_user(assignee_id)
        except discord.HTTPException:
            return str(assignee_id)
    if hasattr(user, 'display_name') and user.display_name:
        return user.display_name
    return user.name


async def _format_task_message(tasks, destination):
    guild = getattr(destination, 'guild', None)
    screen_names = {}
    lines = []
    for task_id, description, assignee_id in tasks:
        if assignee_id not in screen_names:
            screen_names[assignee_id] = await _get_screen_name(assignee_id, guild)
        assignee_name = screen_names[assignee_id]
        description = description.strip()
        if not description:
            description = 'No description provided.'
        lines.append(f'- #{task_id} {assignee_name}\n  {description}')
    return '\n'.join(lines)


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
    message_body = await _format_task_message(tasks, destination)
    await destination.send(f"**Active Tasks**\n{message_body}")


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
@moderator_only()
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
@moderator_only()
async def list_tasks(ctx):
    """List all active tasks."""
    await _send_active_tasks(ctx)


@bot.command(name='complete', aliases=['complete_task'])
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
@moderator_only()
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
        "(Moderator role required for commands unless noted)\n"
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
    _start_web_interface()
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('DISCORD_TOKEN environment variable not set.')
    else:
        bot.run(TOKEN)
