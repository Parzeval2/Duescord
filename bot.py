import os
import asyncio
import sqlite3
from discord.ext import commands

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
bot = commands.Bot(command_prefix='!')

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command(name='register')
async def register(ctx, name: str, paid: bool, *, comment: str = None):
    """Register a user with dues status and optional comment."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO members (name, paid, comment) VALUES (?, ?, ?)',
        (name, int(paid), comment)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Registered {name} with paid={paid}.")

if __name__ == '__main__':
    init_db()
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print('DISCORD_TOKEN environment variable not set.')
    else:
        bot.run(TOKEN)
