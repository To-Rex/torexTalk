# from fastapi import FastAPI
# from contextlib import asynccontextmanager
# from client_manager import start_client, active_clients
# from handlers import observers
# from routes import router
# import asyncio
# import uvicorn
#
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     session_files = list(active_clients.keys())
#     await asyncio.gather(*[start_client(name) for name in session_files], return_exceptions=True)
#
#     yield
#
#     for observer in observers.values():
#         observer.stop()
#         observer.join()
#     await asyncio.gather(*[client.stop() for client in active_clients.values()], return_exceptions=True)
#
# app = FastAPI(lifespan=lifespan)
# app.include_router(router)
#
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8001)



# # main.py
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware  # Add CORS
# from contextlib import asynccontextmanager
# from client_manager import start_client, active_clients
# from handlers import observers
# from routes import router
# from middleware import rate_limit_middleware  # Import from middleware.py
# import asyncio
# import uvicorn
# import logging
# from dotenv import load_dotenv
# import os
#
# # Load environment variables
# load_dotenv()
#
# # Logging setup
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
# # Rate limiting configuration from .env
# RATE_LIMIT = int(os.getenv("RATE_LIMIT", 100))  # Default to 100 if not set
# TIME_WINDOW = int(os.getenv("TIME_WINDOW", 60))  # Default to 60 if not set
# rate_limit_storage: dict = {}
#
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     session_files = list(active_clients.keys())
#     await asyncio.gather(*[start_client(name) for name in session_files], return_exceptions=True)
#
#     yield
#
#     for observer in observers.values():
#         observer.stop()
#         observer.join()
#     await asyncio.gather(*[client.stop() for client in active_clients.values()], return_exceptions=True)
#
# # Initialize FastAPI app
# app = FastAPI(lifespan=lifespan)
#
# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:8001", "http://localhost", "*"],  # "*" for testing
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
# # Include routes
# app.include_router(router)
#
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8001)



from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from client_manager import start_client, active_clients
from handlers import observers
from routes import router
from middleware import rate_limit_middleware
import asyncio
import uvicorn
import logging
from dotenv import load_dotenv
import os
from config import DIRS  # DIRS ni config dan import qilamiz

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration from .env
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 100))  # Default to 100 if not set
TIME_WINDOW = int(os.getenv("TIME_WINDOW", 60))  # Default to 60 if not set
rate_limit_storage: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sessiya fayllarini DIRS["sessions"] dan olish
    sessions_dir = DIRS["sessions"]
    session_files = [f.replace(".session", "") for f in os.listdir(sessions_dir) if f.endswith(".session")]

    if not session_files:
        logger.info("No session files found in sessions directory")
    else:
        logger.info(f"Found session files: {session_files}")
        # Har bir sessiyani avtomatik ishga tushirish
        results = await asyncio.gather(*[start_client(name) for name in session_files], return_exceptions=True)
        for name, result in zip(session_files, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to start session {name}: {result}")

    yield

    # Cleanup: barcha observer va clientlarni to'xtatish
    for observer in observers.values():
        try:
            observer.stop()
            observer.join()
        except Exception as e:
            logger.error(f"Error stopping observer: {e}")
    await asyncio.gather(*[client.stop() for client in active_clients.values()], return_exceptions=True)

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001", "http://localhost", "*"],  # "*" for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)