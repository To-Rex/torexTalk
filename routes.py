from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pyrogram import Client
from pyrogram.errors import PhoneCodeInvalid, SessionPasswordNeeded, PhoneNumberInvalid

from models import (LoginRequest, CodeRequest, PasswordRequest, QuestionRequest,
                   ResponseRequest, EditQuestionRequest, SessionDataRequest)
from utils import (load_json, save_json, get_session_data_path, modify_data, session_data_cache,
                  session_stats_cache, update_stats_cache)
from client_manager import active_clients, start_client, cache_storage
from handlers import update_session_bot
from config import DIRS, logger, DEFAULT_DATA_PATH
import json
import asyncio
import os

router = APIRouter()

@router.get("/get_sessions")
async def get_sessions(include_photos: bool = True):
    async def get_session_info(name: str, client):
        cache_key = f"session_info:{name}"
        if cache_key in cache_storage:
            data = json.loads(cache_storage[cache_key])
            if data.get("profile_photo") and not os.path.exists(data["profile_photo"]):
                data["profile_photo"] = None
            return data
        try:
            me = await client.get_me()
            photo_path = os.path.join(DIRS["photos"], f"{name}_profile.jpg")
            profile_photo = photo_path if os.path.exists(photo_path) else None
            if include_photos and not profile_photo:
                async for photo in client.get_chat_photos("me", limit=1):
                    profile_photo = await client.download_media(photo.file_id, file_name=photo_path)
                    break
            data = {"session_name": name, "first_name": me.first_name, "last_name": me.last_name or "",
                    "username": me.username or "", "id": me.id, "profile_photo": profile_photo, "status": "active",
                    "data_file": get_session_data_path(name)}
            cache_storage[cache_key] = json.dumps(data)
            return data
        except Exception as e:
            return {"session_name": name, "error": str(e), "status": "error"}

    sessions_info = await asyncio.gather(*[get_session_info(n, c) for n, c in active_clients.items()],
                                         return_exceptions=True)
    inactive_sessions = {f.split(".")[0] for f in os.listdir(DIRS["sessions"]) if f.endswith(".session")} - set(
        active_clients.keys())
    sessions_info.extend({"session_name": name, "first_name": "Unknown", "last_name": "", "username": "", "id": None,
                          "profile_photo": None, "status": "inactive",
                          "data_file": get_session_data_path(name) if os.path.exists(
                              get_session_data_path(name)) else None}
                         for name in inactive_sessions)
    return {"sessions": sessions_info}

@router.post("/start_login")
async def start_login(request: LoginRequest, req: Request):
    from client_manager import login_states, API_ID, API_HASH
    session_name = f"temp_{request.phone_number.replace('+', '')}"
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=DIRS["sessions"])
    try:
        await client.connect()
        sent_code = await client.send_code(request.phone_number)
        login_states[request.phone_number] = {"phone_code_hash": sent_code.phone_code_hash,
                                              "session_name": session_name, "client": client}
        logger.info(f"Login started for {request.phone_number} from IP: {req.client.host}")
        return {"message": "Code sent", "phone_code_hash": sent_code.phone_code_hash, "session_name": session_name}
    except PhoneNumberInvalid:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    except Exception as e:
        logger.error(f"Start login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify_code")
async def verify_code(request: CodeRequest):
    from client_manager import login_states
    state = login_states.get(request.phone_number)
    if not state:
        raise HTTPException(status_code=404, detail="Login session not found")
    client = state["client"]
    try:
        await client.sign_in(phone_number=request.phone_number, phone_code_hash=request.phone_code_hash,
                             phone_code=request.code)
        await client.storage.save()
        del login_states[request.phone_number]
        await start_client(state["session_name"])
        return {"message": "Logged in", "session_name": state["session_name"]}
    except SessionPasswordNeeded:
        login_states[request.phone_number]["requires_password"] = True
        return {"message": "Password required", "phone_code_hash": request.phone_code_hash, "requires_password": True}
    except PhoneCodeInvalid:
        raise HTTPException(status_code=400, detail="Invalid code")
    except Exception as e:
        logger.error(f"Verify code error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if request.phone_number in login_states and not login_states[request.phone_number].get("requires_password"):
            await client.disconnect()

@router.post("/verify_password")
async def verify_password(request: PasswordRequest):
    from client_manager import login_states
    state = login_states.get(request.phone_number)
    if not state:
        raise HTTPException(status_code=404, detail="Login session not found")
    client = state["client"]
    try:
        await client.check_password(request.password)
        await client.storage.save()
        del login_states[request.phone_number]
        await start_client(state["session_name"])
        return {"message": "Logged in with 2FA", "session_name": state["session_name"]}
    except Exception as e:
        logger.error(f"Verify password error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid password: {e}")
    finally:
        if request.phone_number in login_states and not login_states[request.phone_number].get("requires_password"):
            await client.disconnect()

@router.get("/get_pairs/{session_name}")
async def get_pairs(session_name: str):
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")
    data = session_data_cache.get(session_name, load_json(session_data_path))
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    return {"pairs": data["data"]["pairs"], "stats": session_stats_cache[session_name]}

async def modify_session_data(session_name: str, operation: str, **kwargs):
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")
    data = session_data_cache.get(session_name, load_json(session_data_path))
    result = modify_data(data, operation, **kwargs)
    save_json(session_data_path, data)
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return result

@router.post("/add_question/{session_name}")
async def add_question(session_name: str, request: QuestionRequest):
    if not request.responses:
        raise HTTPException(status_code=400, detail="At least one response required")
    new_question = await modify_session_data(session_name, "add_question", question=request.question,
                                             responses=request.responses)
    return {"message": f"Question added to {session_name}", "question": new_question}

@router.post("/add_response/{session_name}/{question_id}")
async def add_response(session_name: str, question_id: int, request: ResponseRequest):
    if not await modify_session_data(session_name, "add_response", question_id=question_id, response=request.response):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": f"Response added to question {question_id} in {session_name}"}

@router.post("/add_session_data")
async def add_session_data(request: SessionDataRequest):
    session_data_path = get_session_data_path(request.session_name)
    data = session_data_cache.get(request.session_name, load_json(session_data_path))
    new_pairs = request.data.get("pairs", [])
    max_id = max((pair.get("id", 0) for pair in data["data"]["pairs"]), default=0)
    for pair in new_pairs:
        if "id" not in pair:
            pair["id"] = max_id + 1
            max_id += 1
        data["data"]["pairs"].append(pair)
    save_json(session_data_path, data)
    session_data_cache[request.session_name] = data
    update_stats_cache(request.session_name, data["data"]["pairs"])
    await update_session_bot(request.session_name, session_data_path)
    return {"message": f"Session data added to {request.session_name}"}

@router.get("/export_session/{session_name}")
async def export_session(session_name: str):
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")
    return session_data_cache.get(session_name, load_json(session_data_path))

@router.post("/import_session/{session_name}")
async def import_session(session_name: str, file: UploadFile = File(...)):
    session_data_path = get_session_data_path(session_name)
    data = json.loads((await file.read()).decode("utf-8"))
    save_json(session_data_path, data)
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return {"message": f"Session {session_name} imported"}

@router.put("/edit_question/{session_name}/{question_id}")
async def edit_question(session_name: str, question_id: int, request: EditQuestionRequest):
    if not await modify_session_data(session_name, "edit_question", question_id=question_id, question=request.question,
                                     responses=request.responses):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": f"Question {question_id} edited in {session_name}"}

@router.put("/edit_response/{session_name}/{question_id}/{response_index}")
async def edit_response(session_name: str, question_id: int, response_index: int, request: ResponseRequest):
    if not await modify_session_data(session_name, "edit_response", question_id=question_id,
                                     response_index=response_index, response=request.response):
        raise HTTPException(status_code=404, detail="Response not found")
    return {"message": f"Response {response_index} edited for question {question_id} in {session_name}"}

@router.delete("/delete_question/{session_name}/{question_id}")
async def delete_question(session_name: str, question_id: int):
    if not await modify_session_data(session_name, "delete_question", question_id=question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": f"Question {question_id} deleted from {session_name}"}

@router.delete("/delete_response/{session_name}/{question_id}/{response_index}")
async def delete_response(session_name: str, question_id: int, response_index: int):
    success, has_responses = await modify_session_data(session_name, "delete_response", question_id=question_id,
                                                       response_index=response_index)
    if not success:
        raise HTTPException(status_code=404, detail="Response not found")
    if not has_responses:
        raise HTTPException(status_code=400, detail="Cannot delete last response")
    return {"message": f"Response {response_index} deleted from question {question_id} in {session_name}"}

@router.delete("/delete_session_data/{session_name}")
async def delete_session_data(session_name: str):
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")
    os.remove(session_data_path)
    data = load_json(DEFAULT_DATA_PATH)
    save_json(session_data_path, data)
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return {"message": f"Session data for {session_name} reset"}