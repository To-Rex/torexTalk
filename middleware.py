from fastapi import Request, HTTPException
from config import RATE_LIMIT, TIME_WINDOW, logger
import time

rate_limit_storage: dict = {}

async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"
    now = time.time()
    count, start_time = rate_limit_storage.get(key, (0, now))
    if now - start_time > TIME_WINDOW:
        count, start_time = 1, now
    elif count >= RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    else:
        count += 1
    rate_limit_storage[key] = (count, start_time)
    return await call_next(request)