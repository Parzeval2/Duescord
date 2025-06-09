# Duescord

Duescord is a Discord bot that helps organizations track dues.

This repository provides a minimal baseline for running the bot.

## Getting Started

1. Create a Discord application and bot account.
2. Set the bot token in the `DISCORD_TOKEN` environment variable.
3. Install dependencies with:

```bash
pip install -r requirements.txt
```

4. Run the bot:

```bash
python -m src.bot
```

The bot currently implements a single `!ping` command that responds with `pong`.


## Database Setup

The bot uses a simple SQLite database by default. The database file is
created automatically the first time you run the bot or when
`src.database.init_db()` is called.

To create the database manually, run:

```bash
python -c "import src.database as db; db.init_db()"
```

Set the `DATABASE_PATH` environment variable to change the location of
the database file.
