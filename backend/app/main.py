from fastapi import FastAPI
from fastapi.routing import APIRoute
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api.main import api_router
from app.core.redis import close_redis


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # startup (có thể init redis pool ở đây nếu cần)
    await close_redis()  # shutdown


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)


app.include_router(api_router, prefix=settings.API_V1_STR)
