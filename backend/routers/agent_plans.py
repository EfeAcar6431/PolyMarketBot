import json

from fastapi import APIRouter

from database import get_db

router = APIRouter()


@router.get("/plans")
async def get_plans(strategy: str = "", limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        q = "SELECT * FROM agent_plans WHERE 1=1"
        params: list = []
        if strategy:
            q += " AND strategy = ?"
            params.append(strategy)
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(q, params)
        rows = await cursor.fetchall()
        plans = []
        for r in rows:
            d = dict(r)
            for key in ("context_json", "reasoning_chain", "plan_json"):
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except Exception:
                        pass
            plans.append(d)
        return plans
    finally:
        await db.close()


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM agent_plans WHERE id = ?", (plan_id,))
        row = await cursor.fetchone()
        if not row:
            return {"error": "not found"}
        d = dict(row)
        for key in ("context_json", "reasoning_chain", "plan_json"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    pass
        return d
    finally:
        await db.close()


@router.get("/positions")
async def get_all_positions(status: str = "", strategy: str = "", limit: int = 50):
    from services.position_manager import position_manager
    return await position_manager.get_positions(
        status=status or None,
        strategy=strategy or None,
        limit=limit,
    )
