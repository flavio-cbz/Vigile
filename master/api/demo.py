"""
Vigile — Demo Mode Management
Resets in-memory demo state (proposals, chat sessions).
"""

from fastapi import APIRouter, HTTPException, status

from master.api.demo_data import is_demo, reset_demo_state
from master.api.deps import DB, CurrentUser

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
async def reset_demo(
    claims: CurrentUser,
    db: DB,
) -> dict:
    """Reset all in-memory demo mutable state and clear proposals in database.

    Only callable by the demo user (guest/guest).
    Restores proposals and chat sessions to their default state.
    """
    if not is_demo(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset only available in demo mode",
        )
    from master.core.audit import AuditAction, log_action

    await db.execute("DELETE FROM action_proposals")
    await db.commit()
    await log_action(
        db,
        user_id=claims["sub"],
        action=AuditAction.DEMO_RESET,
        details={},
    )
    reset_demo_state()
    return {"success": True, "message": "Demo state reset successfully"}
