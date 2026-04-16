"""API package."""

from citeo.api.admin_routes import admin_api_router, admin_page_router
from citeo.api.routes import init_services, router

__all__ = [
    "router",
    "admin_page_router",
    "admin_api_router",
    "init_services",
]
