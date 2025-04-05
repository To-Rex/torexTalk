#routes.py

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response
from pyrogram import Client
from pyrogram.errors import PhoneCodeInvalid, SessionPasswordNeeded, PhoneNumberInvalid
from models import (LoginRequest, CodeRequest, PasswordRequest, QuestionRequest,
                   ResponseRequest, EditQuestionRequest, SessionDataRequest)
from utils import (load_json, save_json, get_session_data_path, modify_data, session_data_cache,
                  session_stats_cache, update_stats_cache, stop_client)
from client_manager import active_clients, start_client, cache_storage
from handlers import update_session_bot
from config import DIRS, logger, DEFAULT_DATA_PATH
import json
import asyncio
import os
import zipfile
from io import BytesIO

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

@router.post("/start_session/{session_name}")
async def start_session(session_name: str):
    if session_name in active_clients:
        return {"message": f"Session {session_name} is already active"}
    session_file = os.path.join(DIRS["sessions"], f"{session_name}.session")
    if not os.path.exists(session_file):
        raise HTTPException(status_code=404, detail="Session file not found")
    await start_client(session_name)
    return {"message": f"Session {session_name} started"}

@router.post("/stop_session/{session_name}")
async def stop_session(session_name: str):
    await stop_client(session_name)
    return {"message": f"Session {session_name} stopped"}

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
    logger.info(f"Loaded data for {session_name}: {data}")
    result = modify_data(data, operation, **kwargs)
    logger.info(f"Modified data for {session_name}: {data}")
    save_json(session_data_path, data)
    logger.info(f"Saved data to {session_data_path}")
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return result


@router.post("/add_question/{session_name}")
async def add_question(session_name: str, request: QuestionRequest):
    if not request.responses:
        raise HTTPException(status_code=400, detail="At least one response required")
    new_question = await modify_session_data(session_name, "add_question", question=request.question, responses=request.responses)
    return {"message": f"Question added to {session_name}", "question": new_question}

async def modify_session_data(session_name: str, operation: str, **kwargs):
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")
    data = session_data_cache.get(session_name, load_json(session_data_path))
    logger.info(f"Loaded data for {session_name}: {data}")
    result = modify_data(data, operation, **kwargs)
    logger.info(f"Modified data for {session_name}: {data}")
    save_json(session_data_path, data)
    logger.info(f"Saved data to {session_data_path}")
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return result

@router.post("/add_response/{session_name}/{question_id}")
async def add_response(session_name: str, question_id: int, request: ResponseRequest):
    # Session mavjudligini tekshirish
    session_data_path = get_session_data_path(session_name)
    if not os.path.exists(session_data_path):
        raise HTTPException(status_code=404, detail="Session data not found")

    # modify_session_data ni chaqirish
    result = await modify_session_data(session_name, "add_response", question_id=question_id, response=request.response)
    if not result:
        raise HTTPException(status_code=404, detail=f"Question with ID {question_id} not found in {session_name}")

    return {"message": f"Response added to question {question_id} in {session_name}"}

@router.post("/add_response/{session_name}")
async def add_response(session_name: str, request: ResponseRequest, question: str = None):
    if not question:
        raise HTTPException(status_code=400, detail="Question parameter is required")
    if not await modify_session_data(session_name, "add_response", question=question, response=request.response):
        raise HTTPException(status_code=404, detail=f"Question '{question}' not found in {session_name}")
    return {"message": f"Response added to question '{question}' in {session_name}"}

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

@router.get("/export_all_sessions")
async def export_all_sessions():
    sessions_dir = DIRS["sessions"]
    session_files = [f for f in os.listdir(sessions_dir) if f.endswith(".session")]

    if not session_files:
        logger.info("No session files found in sessions directory")
        raise HTTPException(status_code=404, detail="No session files found in sessions directory")

    # ZIP faylni xotirada yaratish
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for session_file in session_files:
            file_path = os.path.join(sessions_dir, session_file)
            zip_file.write(file_path, session_file)

    buffer.seek(0)
    logger.info(f"Exported all sessions: {session_files}")

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=sessions_archive.zip"}
    )

@router.post("/import_session/")
async def import_session(file: UploadFile = File(...)):
    sessions_dir = DIRS["sessions"]

    # Fayl nomidan session_name ni olish
    session_name = file.filename.replace(".session", "")  # .session kengaytmasini olib tashlaymiz
    session_file = os.path.join(sessions_dir, f"{session_name}.session")
    session_data_path = get_session_data_path(session_name)

    # .session faylni saqlash
    with open(session_file, "wb") as f:
        f.write(await file.read())

    # Session data faylini yaratish (agar mavjud bo'lmasa)
    if not os.path.exists(session_data_path):
        default_data = load_json(DEFAULT_DATA_PATH, default={"data": {"pairs": []}})
        save_json(session_data_path, default_data)
        session_data_cache[session_name] = default_data
        update_stats_cache(session_name, default_data["data"]["pairs"])
        logger.info(f"Session data created for {session_name} at {session_data_path}")

    # Sessiyani avtomatik ishga tushirish
    try:
        await start_client(session_name)
        logger.info(f"Session {session_name} imported and started")
        return {"message": f"Session {session_name} imported and started"}
    except Exception as e:
        logger.error(f"Failed to start session {session_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")

@router.post("/import_sessions")
async def import_sessions(file: UploadFile = File(...)):
    sessions_dir = DIRS["sessions"]
    imported_sessions = []

    # ZIP faylni xotirada ochish
    buffer = BytesIO(await file.read())
    with zipfile.ZipFile(buffer, "r") as zip_file:
        for file_name in zip_file.namelist():
            if file_name.endswith(".session"):
                session_name = file_name.replace(".session", "")
                session_file = os.path.join(sessions_dir, file_name)
                session_data_path = get_session_data_path(session_name)

                # .session faylni saqlash
                with open(session_file, "wb") as f:
                    f.write(zip_file.read(file_name))

                # Session data faylini yaratish (agar mavjud bo'lmasa)
                if not os.path.exists(session_data_path):
                    default_data = load_json(DEFAULT_DATA_PATH, default={"data": {"pairs": []}})
                    save_json(session_data_path, default_data)
                    session_data_cache[session_name] = default_data
                    update_stats_cache(session_name, default_data["data"]["pairs"])
                    logger.info(f"Session data created for {session_name} at {session_data_path}")

                # Sessiyani avtomatik ishga tushirish
                try:
                    await start_client(session_name)
                    imported_sessions.append(session_name)
                except Exception as e:
                    logger.error(f"Failed to start session {session_name}: {e}")
                    # Xato bo'lsa ham davom etamiz, lekin log qoldiramiz

    if not imported_sessions:
        raise HTTPException(status_code=500, detail="No sessions were successfully imported")

    logger.info(f"Imported and started sessions: {imported_sessions}")
    return {"message": "Sessions imported and started", "sessions": imported_sessions}

@router.get("/export_session/{session_name}")
async def export_sessions(session_name: str = None, request: Request = None):
    sessions_dir = DIRS["sessions"]
    session_files = [f for f in os.listdir(sessions_dir) if f.endswith(".session")]

    if not session_files:
        logger.info("No session files found in sessions directory")
        raise HTTPException(status_code=404, detail="No session files found in sessions directory")

    logger.info(f"Found session files: {session_files}")

    if session_name:
        # Bitta sessiya faylini yuklash
        session_file = os.path.join(sessions_dir, f"{session_name}.session")
        if not os.path.exists(session_file):
            logger.error(f"Session file not found: {session_file}")
            raise HTTPException(status_code=404, detail=f"Session {session_name} not found")
        return FileResponse(
            path=session_file,
            filename=f"{session_name}.session",
            media_type="application/octet-stream"
        )
    else:
        # Joriy server URL-ni avtomatik olish
        base_url = str(request.url).rstrip("/")  # So‘rov URL-ni oladi va oxirgi / ni olib tashlaydi
        session_links = [
            {
                "session_name": session_file.replace(".session", ""),
                "download_url": f"{base_url}/{session_file.replace('.session', '')}"
            }
            for session_file in session_files
        ]
        return {"sessions": session_links}

@router.post("/import_session/{session_name}")
async def import_session(session_name: str, file: UploadFile = File(...)):
    session_data_path = get_session_data_path(session_name)
    data = json.loads((await file.read()).decode("utf-8"))
    save_json(session_data_path, data)
    session_data_cache[session_name] = data
    update_stats_cache(session_name, data["data"]["pairs"])
    await update_session_bot(session_name, session_data_path)
    return {"message": f"Session {session_name} imported"}


@router.put("/edit_question/{session_name}")
async def edit_question(session_name: str, request: EditQuestionRequest, old_question: str = None):
    if not old_question:
        raise HTTPException(status_code=400, detail="Old question parameter is required")
    if not await modify_session_data(session_name, "edit_question", question=old_question, new_question=request.question, responses=request.responses):
        raise HTTPException(status_code=404, detail=f"Question '{old_question}' not found")
    return {"message": f"Question '{old_question}' edited in {session_name}"}

@router.put("/edit_response/{session_name}/{question_id}/{response_index}")
async def edit_response(session_name: str, question_id: int, response_index: int, request: ResponseRequest):
    if not await modify_session_data(session_name, "edit_response", question_id=question_id,
                                     response_index=response_index, response=request.response):
        raise HTTPException(status_code=404, detail="Response not found")
    return {"message": f"Response {response_index} edited for question {question_id} in {session_name}"}




@router.delete("/delete_question/{session_name}")
async def delete_question(session_name: str, question: str = None):
    if not question:
        raise HTTPException(status_code=400, detail="Question parameter is required")
    if not await modify_session_data(session_name, "delete_question", question=question):
        raise HTTPException(status_code=404, detail=f"Question '{question}' not found")
    return {"message": f"Question '{question}' deleted from {session_name}"}
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