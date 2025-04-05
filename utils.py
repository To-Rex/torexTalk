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
    if operation == "add_response":
        logger.info(f"Before adding response: {pairs}")
        question = kwargs.get("question")
        response = kwargs.get("response")
        for pair in pairs:
            if pair["question"] == question:
                pair["responses"].append(response)
                logger.info(f"After adding response to question '{question}': {pair}")
                return True
        logger.warning(f"No pair found with question='{question}' in {pairs}")
        return False
    elif operation == "add_question":
        question = kwargs.get("question")
        responses = kwargs.get("responses", [])
        new_pair = {"question": question, "responses": responses}
        pairs.append(new_pair)
        logger.info(f"Added new question: {new_pair}")
        return new_pair
    elif operation == "edit_question":
        old_question = kwargs.get("question")
        new_question = kwargs.get("new_question", old_question)
        responses = kwargs.get("responses")
        for pair in pairs:
            if pair["question"] == old_question:
                pair["question"] = new_question
                if responses is not None:
                    pair["responses"] = responses
                logger.info(f"Edited question '{old_question}' to '{new_question}': {pair}")
                return True
        return False
    elif operation == "edit_response":
        question = kwargs.get("question")
        response_index = kwargs.get("response_index")
        response = kwargs.get("response")
        for pair in pairs:
            if pair["question"] == question and response_index < len(pair["responses"]):
                pair["responses"][response_index] = response
                logger.info(f"Edited response for question '{question}': {pair}")
                return True
        return False
    elif operation == "delete_question":
        question = kwargs.get("question")
        initial_len = len(pairs)
        data["data"]["pairs"] = [p for p in pairs if p["question"] != question]
        logger.info(f"Deleted question '{question}', remaining pairs: {data['data']['pairs']}")
        return len(pairs) != initial_len
    elif operation == "delete_response":
        question = kwargs.get("question")
        response_index = kwargs.get("response_index")
        for pair in pairs:
            if pair["question"] == question and response_index < len(pair["responses"]):
                pair["responses"].pop(response_index)
                logger.info(f"Deleted response from question '{question}': {pair}")
                return True, len(pair["responses"]) > 0
        return False, False

async def stop_client(session_name: str):
    if session_name not in active_clients:
        raise HTTPException(status_code=404, detail="Session is not active")
    client = active_clients[session_name]
    await client.stop()
    del active_clients[session_name]
    logger.info(f"Client stopped for {session_name}")
    return {"message": f"Session {session_name} stopped"}