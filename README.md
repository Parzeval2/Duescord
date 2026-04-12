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
!register <first> [last] <paid> [comment]
```

- `first`: The member's first name.
- `last`: Optional last name.
- `paid`: `True` if dues are paid, `False` otherwise.
- `comment`: Optional comment about the member.

You can remove **all** members with the `!clear_table` command, but you
must confirm the action a second time to prevent accidents.

Use the `!members` command to view a table of all registered members. Each
entry now shows an **ID** which can be used with other commands. Duplicate
names are rejected on registration.

Additional commands:

- `!update <id> <paid> [comment]` – update a member's paid status or comment.
- `!delete <id>` – remove a member.
- `!find <query>` – search names or comments for a keyword.
- `!unpaid` – list only members who have not paid.
- `!stats` – show counts of total, paid and unpaid members.
- `!unpay_all` – mark all members as unpaid.
- `!help` – display a summary of commands.

Members are stored in the `duescord.db` SQLite database.

## Running with Docker

You can also run the bot in a Docker container. The provided image
stores the database in `/data/duescord.db` by default. Mount a host
directory to persist the database between runs:

```bash
# Build the image
docker build -t duescord .

# Run the bot (replace YOUR_TOKEN with your bot token)
docker run -e DISCORD_TOKEN=YOUR_TOKEN \
    -v $(pwd)/data:/data duescord

```

Alternatively, use `docker-compose` which automatically mounts the
`data/` directory:

```bash
DISCORD_TOKEN=YOUR_TOKEN docker compose up
```

The database path can be customised with the `DATABASE_PATH`
environment variable.

### Quick start script

For convenience, a `start.sh` script is provided that builds the Docker
image (if needed) and launches the bot with `docker compose`.

```bash
DISCORD_TOKEN=YOUR_TOKEN ./start.sh
```

The database will be stored in the `data/` directory by default.

## Web interface

Duescord now includes a lightweight web dashboard (enabled by default)
available at `http://localhost:8080`.

Environment variables:

- `WEB_ENABLED` (default: `true`) – enable/disable the web server.
- `WEB_HOST` (default: `0.0.0.0`) – host interface to bind.
- `WEB_PORT` (default: `8080`) – port for the web server.
- `WEB_SECRET_KEY` – Flask session secret (recommended in production).
- `WEB_ADMIN_TOKEN` – required to enable the **Admin SQL Browser** tab.

The dashboard includes tabs for Members, Tasks, and an Admin SQL Browser.
When `WEB_ADMIN_TOKEN` is set, admins can log in through `/admin/login` and
dynamically browse all SQL tables and rows from the database.
