"""Hourly Nedarim external-income sync."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.job import AchnasotSyncResponse
from app.services.achnasot_sync_service import AchnasotSyncService
from app.services.nedarim_client import NedarimApiError

logger = logging.getLogger(__name__)

router = APIRouter()


def _authorized(authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    expected = settings.sync_job_token
    if len(token) != len(expected):
        return False
    return secrets.compare_digest(token, expected)


@router.post("/achnasot-sync", response_model=AchnasotSyncResponse)
async def achnasot_sync(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> AchnasotSyncResponse:
    if not settings.sync_job_token:
        raise HTTPException(status_code=503, detail="Sync job token not configured")
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Invalid sync token")
    if not settings.nedarim_api_password:
        raise HTTPException(status_code=503, detail="Nedarim API password not configured")

    try:
        result = await AchnasotSyncService(db).sync()
    except NedarimApiError as exc:
        logger.warning("achnasot sync failed: %s", exc)
        raise HTTPException(status_code=502, detail="Nedarim request failed") from exc
    return AchnasotSyncResponse.model_validate(result)
