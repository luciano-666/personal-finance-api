from fastapi import APIRouter, Query

from app.crud import get_monthly_summary
from app.schemas import MonthlySummaryResponse
from app.api.deps import SessionDep, CurrentUser

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=MonthlySummaryResponse)
async def read_monthly_summary(
    session: SessionDep,
    current_user: CurrentUser,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
) -> MonthlySummaryResponse:
    summary = await get_monthly_summary(
        session=session, user_id=current_user.id, year=year, month=month
    )
    return summary
