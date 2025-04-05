#utils.py

import json
import os
from cachetools import LRUCache
from config import DIRS, DEFAULT_DATA_PATH, MAX_CACHE_SIZE, logger

# Global caches
session_data_cache = LRUCache(maxsize=MAX_CACHE_SIZE)
session_stats_cache = LRUCache(maxsize=MAX_CACHE_SIZE)

def load_json(file_path: str, default={"data": {"pairs": []}}):
    return json.load(open(file_path, "r", encoding="utf-8")) if os.path.exists(file_path) else default

def save_json(file_path: str, data: dict):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_session_data_path(session_name: str) -> str:
    return os.path.join(DIRS["data"], f"{session_name}_data.json")

def update_stats_cache(session_name: str, pairs: list):
    session_stats_cache[session_name] = {
        "total_questions": len(pairs),
        "total_responses": sum(len(pair["responses"]) for pair in pairs)
    }

def modify_data(data: dict, operation: str, **kwargs):
    pairs = data["data"]["pairs"]
    if operation == "add_question":
        max_id = max((pair.get("id", 0) for pair in pairs), default=0)
        new_pair = {"id": max_id + 1, "question": kwargs["question"], "responses": kwargs["responses"]}
        pairs.append(new_pair)
        return new_pair
    elif operation == "add_response":
        for pair in pairs:
            if pair["id"] == kwargs["question_id"]:
                pair["responses"].append(kwargs["response"])
                return True
        return False
    elif operation == "edit_question":
        for pair in pairs:
            if pair["id"] == kwargs["question_id"]:
                pair["question"] = kwargs.get("question", pair["question"])
                if kwargs.get("responses") is not None:
                    pair["responses"] = kwargs["responses"]
                return True
        return False
    elif operation == "edit_response":
        for pair in pairs:
            if pair["id"] == kwargs["question_id"] and kwargs["response_index"] < len(pair["responses"]):
                pair["responses"][kwargs["response_index"]] = kwargs["response"]
                return True
        return False
    elif operation == "delete_question":
        initial_len = len(pairs)
        data["data"]["pairs"] = [p for p in pairs if p["id"] != kwargs["question_id"]]
        return len(pairs) != initial_len
    elif operation == "delete_response":
        for pair in pairs:
            if pair["id"] == kwargs["question_id"] and kwargs["response_index"] < len(pair["responses"]):
                pair["responses"].pop(kwargs["response_index"])
                return True, len(pair["responses"]) > 0
        return False, False


# Sessiyani to‘xtatish funksiyasi
async def stop_client(session_name: str):
    if session_name not in active_clients:
        raise HTTPException(status_code=404, detail="Session is not active")
    client = active_clients[session_name]
    await client.stop()
    del active_clients[session_name]
    logger.info(f"Client stopped for {session_name}")
    return {"message": f"Session {session_name} stopped"}