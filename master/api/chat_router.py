"""
Vigile — Chat Router (shared definition)
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/chat", tags=["chat"])
