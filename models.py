#models.py

from pydantic import BaseModel
from typing import List, Dict

class LoginRequest(BaseModel):
    phone_number: str

class CodeRequest(BaseModel):
    phone_number: str
    code: str
    phone_code_hash: str

class PasswordRequest(BaseModel):
    phone_number: str
    password: str
    phone_code_hash: str

class QuestionRequest(BaseModel):
    question: str
    responses: List[str]

class ResponseRequest(BaseModel):
    response: str

class EditQuestionRequest(BaseModel):
    question: str = None
    responses: List[str] = None

class SessionDataRequest(BaseModel):
    session_name: str
    data: dict