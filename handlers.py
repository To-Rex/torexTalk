#handlers.py

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils import load_json, update_stats_cache, session_data_cache, get_session_data_path
from config import logger, DIRS
from ai.response import CustomChatBot

observers: dict = {}
session_bots: dict = {}

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, session_name: str):
        self.session_name = session_name

    def on_modified(self, event):
        if not event.is_directory and event.src_path == get_session_data_path(self.session_name):
            try:
                data = load_json(event.src_path)
                session_data_cache[self.session_name] = data
                update_stats_cache(self.session_name, data["data"]["pairs"])
                logger.info(f"Cache updated for {self.session_name}")
            except Exception as e:
                logger.error(f"Cache update error for {self.session_name}: {e}")

async def update_session_bot(session_name: str, session_data_path: str):
    session_bots[session_name] = CustomChatBot(session_data_path)
    from client_manager import start_client, active_clients
    if session_name in active_clients:
        await start_client(session_name)