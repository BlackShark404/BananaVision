"""Keep CORS outside Starlette's error handler, including unexpected 500s."""
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import get_settings


class CorsFastAPI(FastAPI):
    def build_middleware_stack(self):
        return CORSMiddleware(
            super().build_middleware_stack(),
            allow_origins=get_settings().app_cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
