#!/usr/bin/env python3
import os
import sys
import asyncio
import argparse
import getpass
import json
from datetime import datetime, timedelta
from typing import Optional, List
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv

load_dotenv()

SESSION_DIR = "sessions"
os.makedirs(SESSION_DIR, exist_ok=True)

DEPTH_MAPPING = {
    '1week': 7,
    '1month': 30,
    '3months': 90,
    '6months': 180,
    '1year': 365,
    'all': None,
}


def _get_credentials():
    """Read API credentials from environment."""
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    if not api_id or not api_hash:
        raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in environment or .env file")
    return int(api_id), api_hash


async def get_client(api_id: int, api_hash: str) -> TelegramClient:
    """Connect and return an authorized client, or raise if not authenticated."""
    session_name = f"{SESSION_DIR}/session_{api_id}"
    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        raise SystemExit("Not authenticated. Run 'auth' first.")

    return client


# ---- Core async logic (returns strings) ----

async def _list_channels(api_id: int, api_hash: str) -> str:
    """List joined channels and return as formatted string."""
    client = await get_client(api_id, api_hash)
    try:
        channels = []
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, Channel) and not dialog.entity.megagroup:
                channels.append({
                    'id': str(dialog.entity.id),
                    'title': dialog.title,
                    'username': dialog.entity.username,
                    'members': getattr(dialog.entity, 'participants_count', 0) or 0,
                })

        output = f"Found {len(channels)} channel(s):\n\n"
        for ch in channels:
            username = f" (@{ch['username']})" if ch['username'] else ""
            output += f"  [{ch['id']}] {ch['title']}{username}  — {ch['members']} members\n"
        return output
    finally:
        await client.disconnect()


async def _search_channel(api_id: int, api_hash: str, channel_id: str, keyword: str,
                           limit: int = 1000, days_back: Optional[int] = None) -> str:
    """Search messages in a single channel and return as formatted string."""
    client = await get_client(api_id, api_hash)
    try:
        channel = await client.get_entity(int(channel_id))

        offset_date = None
        if days_back:
            offset_date = datetime.now() - timedelta(days=days_back)

        results = []
        count = 0

        async for message in client.iter_messages(
            channel, limit=limit, offset_date=offset_date, search=keyword
        ):
            if message.text and keyword.lower() in message.text.lower():
                results.append({
                    'id': message.id,
                    'date': message.date.isoformat() if message.date else None,
                    'sender_id': str(message.sender_id) if message.sender_id else 'unknown',
                    'text': message.text,
                    'channel': channel.title,
                })
            count += 1

        output = f"Found {len(results)} match(es) in {channel.title} (scanned {count} messages):\n\n"
        for msg in results:
            date = msg['date'][:10] if msg['date'] else '???'
            text_preview = msg['text'][:120].replace('\n', ' ')
            output += f"  [{date}] (msg {msg['id']}) {text_preview}\n"
        return output
    finally:
        await client.disconnect()


async def _search_multiple_channels(api_id: int, api_hash: str, keyword: str,
                                     channel_ids: List[str], depth: str = '1month',
                                     limit: int = 1000) -> str:
    """Search across multiple channels and return as formatted string."""
    client = await get_client(api_id, api_hash)
    days_back = DEPTH_MAPPING.get(depth)

    try:
        all_results = []
        total = len(channel_ids)
        output = ""

        for i, channel_id in enumerate(channel_ids):
            try:
                channel = await client.get_entity(int(channel_id))

                offset_date = None
                if days_back:
                    offset_date = datetime.now() - timedelta(days=days_back)

                count = 0
                async for message in client.iter_messages(
                    channel, limit=limit, offset_date=offset_date, search=keyword
                ):
                    if message.text and keyword.lower() in message.text.lower():
                        all_results.append({
                            'id': message.id,
                            'date': message.date.isoformat() if message.date else None,
                            'sender_id': str(message.sender_id) if message.sender_id else 'unknown',
                            'text': message.text,
                            'channel': channel.title,
                            'channel_id': channel_id,
                        })
                    count += 1

            except Exception as e:
                output += f"  Error on channel {channel_id}: {e}\n"

            if i < total - 1:
                await asyncio.sleep(2)

        output += f"Total: {len(all_results)} match(es) across {total} channel(s):\n\n"
        for msg in all_results:
            date = msg['date'][:10] if msg['date'] else '???'
            text_preview = msg['text'][:120].replace('\n', ' ')
            output += f"  [{msg['channel']}] [{date}] (msg {msg['id']}) {text_preview}\n"
        return output
    finally:
        await client.disconnect()


# ---- Agent-friendly tool functions (sync wrappers with typed params) ----

def _run_async(coro):
    """Run an async coroutine, handling both sync and async calling contexts."""
    try:
        asyncio.get_running_loop()
        # Already inside an async context (e.g. Agno agent) — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)


def list_channels() -> str:
    """List all Telegram channels the user is a member of, showing channel IDs, titles, and member counts.

    Returns:
        str: Formatted list of channels with their IDs, titles, usernames, and member counts.
    """
    try:
        api_id, api_hash = _get_credentials()
        return _run_async(_list_channels(api_id, api_hash))
    except Exception as e:
        return f"Error listing channels: {str(e)}"


def search_channel(channel_id: str, keyword: str, limit: int = 1000,
                   days_back: Optional[int] = None) -> str:
    """Search messages in a single Telegram channel by keyword.

    Args:
        channel_id: The numeric ID of the channel to search (use list_channels to find IDs).
        keyword: The search term to look for in messages.
        limit: Maximum number of messages to scan (default 1000).
        days_back: Only search messages from the last N days. None searches all history.

    Returns:
        str: Matching messages with dates, message IDs, and text previews.
    """
    try:
        api_id, api_hash = _get_credentials()
        return _run_async(_search_channel(api_id, api_hash, channel_id, keyword, limit, days_back))
    except Exception as e:
        return f"Error searching channel: {str(e)}"


def search_multiple_channels(keyword: str, channel_ids: str, depth: str = '1month',
                              limit: int = 1000) -> str:
    """Search for a keyword across multiple Telegram channels.

    Args:
        keyword: The search term to look for in messages.
        channel_ids: Comma-separated channel IDs to search (e.g. "1234567,2345678,3456789").
        depth: How far back to search. One of: 1week, 1month, 3months, 6months, 1year, all (default: 1month).
        limit: Maximum number of messages to scan per channel (default 1000).

    Returns:
        str: Matching messages from all channels with channel names, dates, and text previews.
    """
    try:
        api_id, api_hash = _get_credentials()
        ids = [cid.strip() for cid in channel_ids.split(",")]
        return _run_async(_search_multiple_channels(api_id, api_hash, keyword, ids, depth, limit))
    except Exception as e:
        return f"Error searching channels: {str(e)}"


def get_telegram_search_tools():
    """Get telegram search tools as a list for use with Agno agents."""
    return [list_channels, search_channel, search_multiple_channels]


# ---- CLI entry point (unchanged) ----

async def cmd_auth(args):
    """Authenticate with Telegram interactively."""
    session_name = f"{SESSION_DIR}/session_{args.api_id}"
    client = TelegramClient(session_name, args.api_id, args.api_hash)
    await client.connect()

    if await client.is_user_authorized():
        print("Already authenticated.")
        await client.disconnect()
        return

    await client.send_code_request(args.phone)
    print(f"Verification code sent to {args.phone}")

    code = input("Enter the code: ").strip()

    try:
        await client.sign_in(args.phone, code)
    except SessionPasswordNeededError:
        password = getpass.getpass("2FA password required: ")
        await client.sign_in(password=password)

    print("Authentication successful.")
    await client.disconnect()


async def cmd_channels(args):
    """List joined channels."""
    result = await _list_channels(args.api_id, args.api_hash)
    if args.json:
        # Re-run to get JSON format for CLI
        client = await get_client(args.api_id, args.api_hash)
        try:
            channels = []
            async for dialog in client.iter_dialogs():
                if isinstance(dialog.entity, Channel) and not dialog.entity.megagroup:
                    channels.append({
                        'id': str(dialog.entity.id),
                        'title': dialog.title,
                        'username': dialog.entity.username,
                        'members': getattr(dialog.entity, 'participants_count', 0) or 0,
                    })
            print(json.dumps(channels, indent=2))
        finally:
            await client.disconnect()
    else:
        print(result)


async def cmd_search(args):
    """Search messages in a single channel."""
    if args.json:
        client = await get_client(args.api_id, args.api_hash)
        try:
            channel = await client.get_entity(int(args.channel))
            offset_date = None
            if args.days_back:
                offset_date = datetime.now() - timedelta(days=args.days_back)
            results = []
            async for message in client.iter_messages(
                channel, limit=args.limit, offset_date=offset_date, search=args.keyword
            ):
                if message.text and args.keyword.lower() in message.text.lower():
                    results.append({
                        'id': message.id,
                        'date': message.date.isoformat() if message.date else None,
                        'sender_id': str(message.sender_id) if message.sender_id else 'unknown',
                        'text': message.text,
                        'channel': channel.title,
                    })
            print(json.dumps(results, indent=2, default=str))
        finally:
            await client.disconnect()
    else:
        result = await _search_channel(args.api_id, args.api_hash, args.channel, args.keyword,
                                        args.limit, args.days_back)
        print(result)


async def cmd_long_search(args):
    """Search across multiple channels."""
    if args.json:
        client = await get_client(args.api_id, args.api_hash)
        days_back = DEPTH_MAPPING.get(args.depth)
        try:
            all_results = []
            for i, channel_id in enumerate(args.channels):
                try:
                    channel = await client.get_entity(int(channel_id))
                    offset_date = None
                    if days_back:
                        offset_date = datetime.now() - timedelta(days=days_back)
                    async for message in client.iter_messages(
                        channel, limit=args.limit, offset_date=offset_date, search=args.keyword
                    ):
                        if message.text and args.keyword.lower() in message.text.lower():
                            all_results.append({
                                'id': message.id,
                                'date': message.date.isoformat() if message.date else None,
                                'sender_id': str(message.sender_id) if message.sender_id else 'unknown',
                                'text': message.text,
                                'channel': channel.title,
                                'channel_id': channel_id,
                            })
                except Exception as e:
                    print(f"  Error on channel {channel_id}: {e}", file=sys.stderr)
                if i < len(args.channels) - 1:
                    await asyncio.sleep(2)
            print(json.dumps(all_results, indent=2, default=str))
        finally:
            await client.disconnect()
    else:
        result = await _search_multiple_channels(args.api_id, args.api_hash, args.keyword,
                                                  args.channels, args.depth, args.limit)
        print(result)


def main():
    parser = argparse.ArgumentParser(
        prog='telegram-search',
        description='Search Telegram channel messages from the command line',
    )
    parser.add_argument('--api-id', type=int, default=os.getenv('TELEGRAM_API_ID'), help='Telegram API ID (or set TELEGRAM_API_ID env var)')
    parser.add_argument('--api-hash', default=os.getenv('TELEGRAM_API_HASH'), help='Telegram API hash (or set TELEGRAM_API_HASH env var)')

    sub = parser.add_subparsers(dest='command', required=True)

    # auth
    p_auth = sub.add_parser('auth', help='Authenticate with Telegram')
    p_auth.add_argument('phone', help='Phone number (international format, e.g. +1234567890)')

    # channels
    p_ch = sub.add_parser('channels', help='List your channels')
    p_ch.add_argument('--json', action='store_true', help='Output as JSON')

    # search
    p_s = sub.add_parser('search', help='Search messages in a channel')
    p_s.add_argument('channel', help='Channel ID')
    p_s.add_argument('keyword', help='Search keyword')
    p_s.add_argument('--limit', type=int, default=1000, help='Max messages to scan (default 1000)')
    p_s.add_argument('--days-back', type=int, help='Only search messages from the last N days')
    p_s.add_argument('--json', action='store_true', help='Output as JSON')

    # long-search
    p_ls = sub.add_parser('long-search', help='Search across multiple channels')
    p_ls.add_argument('keyword', help='Search keyword')
    p_ls.add_argument('channels', nargs='+', help='Channel IDs to search')
    p_ls.add_argument('--depth', choices=DEPTH_MAPPING.keys(), default='1month', help='How far back to search (default 1month)')
    p_ls.add_argument('--limit', type=int, default=1000, help='Max messages per channel (default 1000)')
    p_ls.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    if not args.api_id or not args.api_hash:
        parser.error('--api-id and --api-hash are required (or set API_ID / API_HASH env vars)')

    commands = {
        'auth': cmd_auth,
        'channels': cmd_channels,
        'search': cmd_search,
        'long-search': cmd_long_search,
    }

    asyncio.run(commands[args.command](args))


if __name__ == '__main__':
    main()
