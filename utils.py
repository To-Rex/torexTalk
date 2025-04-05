# utils.py

import json
import os
from cachetools import LRUCache
from config import DIRS, DEFAULT_DATA_PATH, MAX_CACHE_SIZE, logger
from fastapi import HTTPException

# Global o'zgaruvchilar
session_data_cache = LRUCache(maxsize=MAX_CACHE_SIZE)  # Sessiya ma'lumotlari uchun kesh
session_stats_cache = LRUCache(maxsize=MAX_CACHE_SIZE)  # Sessiya statistikasi uchun kesh
active_clients = {}  # Faol mijozlarni saqlash uchun lug'at (sessiya nomi -> mijoz obyekti)

# JSON faylni yuklash funksiyasi
def load_json(file_path: str, default={"data": {"pairs": []}}):
    """Berilgan fayl yo'lidan JSON ma'lumotlarini yuklaydi, agar fayl bo'lmasa default qiymatni qaytaradi."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

# JSON faylni saqlash funksiyasi
def save_json(file_path: str, data: dict):
    """Berilgan ma'lumotlarni JSON faylga saqlaydi."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Sessiya ma'lumotlari uchun fayl yo'lini olish
def get_session_data_path(session_name: str) -> str:
    """Sessiya nomiga asosan ma'lumot faylining yo'lini qaytaradi."""
    return os.path.join(DIRS["data"], f"{session_name}_data.json")

# Sessiya statistikasini yangilash
def update_stats_cache(session_name: str, pairs: list):
    """Sessiya statistikasini (savollar va javoblar soni) keshda yangilaydi."""
    session_stats_cache[session_name] = {
        "total_questions": len(pairs),
        "total_responses": sum(len(pair["responses"]) for pair in pairs)
    }

# Ma'lumotlarni o'zgartirish funksiyasi
def modify_data(data: dict, operation: str, **kwargs):
    """Sessiya ma'lumotlarini turli operatsiyalar bilan o'zgartiradi (qo'shish, tahrirlash, o'chirish)."""
    pairs = data["data"]["pairs"]

    if operation == "add_response":
        # Mavjud savolga yangi javob qo'shish
        question = kwargs.get("question")
        response = kwargs.get("response")
        for pair in pairs:
            if pair["question"] == question:
                pair["responses"].append(response)
                logger.info(f"'{question}' savoliga javob qo'shildi: {pair}")
                return True
        logger.warning(f"'{question}' savoli topilmadi: {pairs}")
        return False

    elif operation == "add_question":
        # Yangi savol qo'shish
        question = kwargs.get("question")
        responses = kwargs.get("responses", [])
        new_pair = {"question": question, "responses": responses}
        pairs.append(new_pair)
        logger.info(f"Yangi savol qo'shildi: {new_pair}")
        return new_pair

    elif operation == "edit_question":
        # Savolni tahrirlash
        old_question = kwargs.get("question")
        new_question = kwargs.get("new_question", old_question)
        responses = kwargs.get("responses")
        for pair in pairs:
            if pair["question"] == old_question:
                pair["question"] = new_question
                if responses is not None:
                    pair["responses"] = responses
                logger.info(f"'{old_question}' savoli '{new_question}' ga o'zgartirildi: {pair}")
                return True
        logger.warning(f"'{old_question}' savoli topilmadi")
        return False

    elif operation == "edit_response":
        # Javobni tahrirlash
        question = kwargs.get("question")
        response_index = kwargs.get("response_index")
        response = kwargs.get("response")
        for pair in pairs:
            if pair["question"] == question and response_index < len(pair["responses"]):
                pair["responses"][response_index] = response
                logger.info(f"'{question}' savolidagi javob tahrirlandi: {pair}")
                return True
        logger.warning(f"'{question}' savoli yoki javob indeksi topilmadi")
        return False

    elif operation == "delete_question":
        # Savolni o'chirish
        question = kwargs.get("question")
        initial_len = len(pairs)
        data["data"]["pairs"] = [p for p in pairs if p["question"] != question]
        logger.info(f"'{question}' savoli o'chirildi, qoldiq juftliklar: {data['data']['pairs']}")
        return len(pairs) != initial_len

    elif operation == "delete_response":
        # Javobni o'chirish
        question = kwargs.get("question")
        response_index = kwargs.get("response_index")
        for pair in pairs:
            if pair["question"] == question and response_index < len(pair["responses"]):
                pair["responses"].pop(response_index)
                logger.info(f"'{question}' savolidan javob o'chirildi: {pair}")
                return True, len(pair["responses"]) > 0
        logger.warning(f"'{question}' savoli yoki javob indeksi topilmadi")
        return False, False


async def start_client(session_name: str):
    # Agar sessiya faol bo‘lsa, avval to‘xtatamiz
    if session_name in active_clients:
        await active_clients[session_name].stop()
        del active_clients[session_name]

    # Sessiya fayli borligini tekshiramiz
    session_file = os.path.join(DIRS["sessions"], f"{session_name}.session")
    if not os.path.exists(session_file):
        logger.error(f"{session_name} sessiya fayli topilmadi")
        return {"message": f"{session_name} sessiya fayli topilmadi"}

    logger.info(f"{session_name} uchun mijozni boshlaymiz")
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=DIRS["sessions"])

    # Ma'lumot faylini tayyorlaymiz
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        logger.info(f"{session_name} uchun ma'lumot fayli yo'q, yangi yaratamiz")
        data = load_json(DEFAULT_DATA_PATH)
        save_json(session_data_path, data)
        session_data_cache[session_name] = data
        update_stats_cache(session_name, data["data"]["pairs"])

    from handlers import update_session_bot
    logger.info(f"{session_name} uchun botni yangilaymiz")
    await update_session_bot(session_name, session_data_path)

    # Avtomatik javob berish funksiyasi
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
        await client.send_message(
            message.chat.id,
            response,
            reply_to_message_id=message.id if len(timestamps) >= REPLY_THRESHOLD and random.random() < 0.5 else None
        )

    # Mijozni boshlash
    try:
        await client.start()
        active_clients[session_name] = client
        logger.info(f"{session_name} muvaffaqiyatli boshlandi. Faol sessiyalar: {list(active_clients.keys())}")
        return {"message": f"{session_name} muvaffaqiyatli boshlandi"}
    except Exception as e:
        logger.error(f"{session_name} ni boshlashda xato: {str(e)}")
        return {"message": f"Xato: {str(e)}"}


async def stop_client(session_name: str):
    if session_name not in active_clients:
        logger.warning(f"{session_name} faol emas ichki tekshiruvda. Faol sessiyalar: {list(active_clients.keys())}")
        return {"message": f"Sessiya {session_name} faol emas"}

    client = active_clients[session_name]
    try:
        await client.stop()  # disconnect() o'rniga stop() ishlatamiz
        del active_clients[session_name]
        logger.info(f"{session_name} sessiyasi to'xtatildi. Active clients after stop: {list(active_clients.keys())}")
        return {"message": f"Sessiya {session_name} to'xtatildi"}
    except Exception as e:
        logger.error(f"Sessiyani to'xtatishda xato: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ichki server xatosi: {str(e)}")

