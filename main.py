# main.py

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
from config import DIRS

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration from .env
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 100))
TIME_WINDOW = int(os.getenv("TIME_WINDOW", 60))
rate_limit_storage: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    sessions_dir = DIRS["sessions"]
    session_files = [f.replace(".session", "") for f in os.listdir(sessions_dir) if f.endswith(".session")]

    if not session_files:
        logger.info("No session files found in sessions directory")
    else:
        logger.info(f"Found session files: {session_files}")
        tasks = [start_client(name) for name in session_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(session_files, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to start session {name}: {str(result)}")
            else:
                logger.info(f"Successfully started session {name}")

    yield

    # Cleanup
    logger.info("Shutting down observers and clients")
    for observer in observers.values():
        try:
            observer.stop()
            observer.join()
        except Exception as e:
            logger.error(f"Error stopping observer: {e}")
    await asyncio.gather(*[client.stop() for client in active_clients.values()], return_exceptions=True)
    logger.info("Shutdown complete")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
   # allow_origins=["http://localhost:8001", "http://localhost", "*"],
    #Access-Control-Allow-Origin: *

    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

if __name__ == "__main__":
    #uvicorn.run(app, host="0.0.0.0", port=8001)
    uvicorn.run(app, port=8001)
    #uvicorn.run(app)