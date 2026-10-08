from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from livekit import api as lkapi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..parsing import parse_phone_number
from .db import PhoneRecord, to_naive_utc, utcnow_naive
from .schemas import (
    Language,
    ParseRequest,
    ParseResponse,
    PhoneCreate,
    PhoneOut,
    PhoneStats,
    TokenResponse,
)

router = APIRouter(prefix="/api")


def get_session(request: Request):
    yield from request.app.state.db.session()


SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/phone", response_model=PhoneOut, status_code=status.HTTP_201_CREATED)
def create_phone(payload: PhoneCreate, session: SessionDep) -> PhoneRecord:
    """Save a validated phone number (validation happens in ``PhoneCreate``)."""
    record = PhoneRecord(
        raw_transcript=payload.raw_transcript,
        parsed_number=payload.parsed_number,
        language=payload.language,
        collected_at=to_naive_utc(payload.collected_at) if payload.collected_at else utcnow_naive(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/phone", response_model=list[PhoneOut])
def list_phones(
    session: SessionDep,
    search: Annotated[str | None, Query(description="Substring of the phone number")] = None,
    language: Language | None = None,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[PhoneRecord]:
    """List collected numbers, newest first, with optional filters."""
    stmt = select(PhoneRecord)
    if search:
        digits = "".join(ch for ch in search if ch.isdigit())
        stmt = stmt.where(PhoneRecord.parsed_number.contains(digits))
    if language:
        stmt = stmt.where(PhoneRecord.language == language)
    if date_from:
        stmt = stmt.where(PhoneRecord.collected_at >= to_naive_utc(date_from))
    if date_to:
        stmt = stmt.where(PhoneRecord.collected_at <= to_naive_utc(date_to))
    stmt = stmt.order_by(PhoneRecord.collected_at.desc(), PhoneRecord.id.desc()).limit(limit)
    return list(session.scalars(stmt))


@router.get("/phone/stats", response_model=PhoneStats)
def phone_stats(session: SessionDep) -> PhoneStats:
    rows = session.execute(
        select(PhoneRecord.language, func.count()).group_by(PhoneRecord.language)
    ).all()
    by_language: dict[str, int] = {"en": 0, "hi": 0, "mixed": 0}
    by_language.update({lang: count for lang, count in rows})
    return PhoneStats(total=sum(by_language.values()), by_language=by_language)


@router.delete("/phone/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phone(record_id: int, session: SessionDep) -> Response:
    record = session.get(PhoneRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/parse", response_model=ParseResponse)
def parse(payload: ParseRequest) -> ParseResponse:
    """Debug helper: run the deterministic parser on a transcript."""
    result = parse_phone_number(payload.transcript)
    return ParseResponse(
        digits=result.digits,
        digit_count=result.digit_count,
        language=result.language,
        corrected=result.corrected,
        is_valid=result.is_valid,
        error=result.error.value if result.error else None,
    )


@router.get("/token", response_model=TokenResponse)
def create_token(room: str | None = None, identity: str | None = None) -> TokenResponse:
    """Mint a LiveKit participant token so a client can join a room with the agent."""
    settings = get_settings()
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=500, detail="LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set")

    room_name = room or f"phone-{uuid.uuid4().hex[:8]}"
    identity = identity or f"user-{uuid.uuid4().hex[:6]}"
    token = (
        lkapi.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_grants(lkapi.VideoGrants(room_join=True, room=room_name))
    )
    if settings.agent_name:
        # explicit dispatch of the named agent into this room
        token = token.with_room_config(
            lkapi.RoomConfiguration(agents=[lkapi.RoomAgentDispatch(agent_name=settings.agent_name)])
        )
    return TokenResponse(
        server_url=settings.livekit_url, room_name=room_name, participant_token=token.to_jwt()
    )
