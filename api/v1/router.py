"""API v1 master router assembling endpoint modules."""

from fastapi import APIRouter

from api.v1.endpoints import certificates, templates

api_router = APIRouter()
api_router.include_router(certificates.router)
api_router.include_router(templates.router)
