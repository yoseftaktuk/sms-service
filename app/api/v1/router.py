from fastapi import APIRouter

from app.api.v1.endpoints import jobs, transactions

api_router = APIRouter()
api_router.include_router(transactions.router, prefix="/webhooks/nedarim", tags=["webhooks"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
