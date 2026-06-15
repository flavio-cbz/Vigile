from fastapi import APIRouter, HTTPException, status

from master.api.demo_data import is_demo, reset_demo_state
from master.api.deps import DB, CurrentUser

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
async def reset_demo(
    claims: CurrentUser,
    db: DB,
) -> dict:
    """Reset demo mutable state and clear proposals. Only callable by the demo user."""
    if not is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset only available in demo mode",
        )
    await db.execute("DELETE FROM action_proposals")
    await db.commit()
    reset_demo_state()
    return {"success": True, "message": "Demo state reset successfully"}
