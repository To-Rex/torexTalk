# client_manager.py

import os
from pyrogram import Client, filters
from config import API_ID, API_HASH, DIRS, REPLY_INTERVAL, REPLY_THRESHOLD, logger, DEFAULT_DATA_PATH
from utils import load_json, save_json, get_session_data_path, session_data_cache, update_stats_cache
from handlers import session_bots
import asyncio
import random
import time

active_clients: dict = {}
cache_storage: dict = {}
message_timestamps: dict = {}
login_states: dict = {}


async def start_client(session_name: str):
    if session_name in active_clients:
        await active_clients[session_name].stop()
        del active_clients[session_name]

    logger.info(f"Attempting to initialize client for {session_name}")
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=DIRS["sessions"])
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        logger.info(f"Session data not found for {session_name}, creating default")
        data = load_json(DEFAULT_DATA_PATH)
        save_json(session_data_path, data)
        session_data_cache[session_name] = data
        update_stats_cache(session_name, data["data"]["pairs"])
    from handlers import update_session_bot
    logger.info(f"Updating session bot for {session_name}")
    await update_session_bot(session_name, session_data_path)

    @client.on_message((filters.text | filters.voice) & filters.private)
    async def auto_reply(_, message):
        now = time.time()
        user_id = message.from_user.id
        my_id = (await client.get_me()).id
        if message.from_user.is_bot or user_id == my_id:
            return
        timestamps = message_timestamps.setdefault(user_id, [])
        timestamps.append(now)
        timestamps[:] = [ts for ts in timestamps if now - ts <= REPLY_INTERVAL]
        if len(timestamps) < REPLY_THRESHOLD and (timestamps[-1] - timestamps[0] > REPLY_INTERVAL):
            return
        await asyncio.sleep(random.randint(3, 6))
        text = message.text or "aaauuudddiiiooo"
        response = session_bots[session_name].question(text)
        if not response or response in ("None", ""):
            return
        await client.send_message(message.chat.id, response, reply_to_message_id=message.id if len(
            timestamps) >= REPLY_THRESHOLD and random.random() < 0.5 else None)

    try:
        logger.info(f"Starting client for {session_name}")
        await client.start()
        active_clients[session_name] = client
        logger.info(f"Client successfully started for {session_name}")
    except Exception as e:
        logger.error(f"Failed to start client {session_name}: {str(e)}")
        raise