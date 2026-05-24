from fastapi.routing import APIRouter

from app.api.routes import users, login, transactions, categories, budgets

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(login.router)
api_router.include_router(transactions.router)
api_router.include_router(categories.router)
api_router.include_router(budgets.router)
