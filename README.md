# Duescord

A simple Discord bot that tracks member dues using a local SQLite database.

## Requirements

- Python 3.8+
- `discord.py` library

Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Bot

Set your Discord bot token as an environment variable:

```bash
export DISCORD_TOKEN="your bot token here"
```

Then start the bot:

```bash
python bot.py
```

Use the `!register` command in your server to add a member:

```
!register <name> <paid> [comment]
```

- `name`: The member's name.
- `paid`: `True` if dues are paid, `False` otherwise.
- `comment`: Optional comment about the member.

Members are stored in the `duescord.db` SQLite database.
