import json
from fastapi import APIRouter, Query

from database import get_db
from models import TradeOut, TradeStats

router = APIRouter()


@router.get("", response_model=list[TradeOut])
async def list_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    side: str | None = None,
    status: str | None = None,
):
    db = await get_db()
    try:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []
        if side:
            query += " AND side = ?"
            params.append(side)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


@router.get("/stats", response_model=TradeStats)
async def trade_stats():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM trades")
        total = (await cursor.fetchone())["cnt"]

        cursor = await db.execute("SELECT COALESCE(SUM(pnl), 0) as total FROM trades")
        total_pnl = float((await cursor.fetchone())["total"])

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM trades WHERE pnl > 0")
        wins = (await cursor.fetchone())["cnt"]

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM trades WHERE pnl < 0")
        losses = (await cursor.fetchone())["cnt"]

        settled = wins + losses
        win_rate = (wins / settled * 100) if settled > 0 else 0.0

        cursor = await db.execute("SELECT MAX(pnl) as best FROM trades")
        best = float((await cursor.fetchone())["best"] or 0)

        cursor = await db.execute("SELECT MIN(pnl) as worst FROM trades")
        worst = float((await cursor.fetchone())["worst"] or 0)

        avg = total_pnl / total if total > 0 else 0.0

        return TradeStats(
            total_trades=total,
            total_pnl=round(total_pnl, 2),
            win_count=wins,
            loss_count=losses,
            win_rate=round(win_rate, 1),
            best_trade=round(best, 2),
            worst_trade=round(worst, 2),
            avg_trade_pnl=round(avg, 2),
        )
    finally:
        await db.close()


@router.get("/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    level: str | None = None,
):
    db = await get_db()
    try:
        query = "SELECT * FROM agent_logs WHERE 1=1"
        params: list = []
        if level:
            query += " AND level = ?"
            params.append(level)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
            result.append(d)
        return result
    finally:
        await db.close()


@router.get("/pnl-series")
async def pnl_series(days: int = Query(30, ge=1, le=365)):
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT DATE(created_at) as date, SUM(pnl) as daily_pnl
            FROM trades
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT ?""",
            (days,),
        )
        rows = await cursor.fetchall()
        series = [{"date": row["date"], "pnl": round(float(row["daily_pnl"]), 2)} for row in rows]
        series.reverse()

        cumulative = 0.0
        for point in series:
            cumulative += point["pnl"]
            point["cumulative_pnl"] = round(cumulative, 2)

        return series
    finally:
        await db.close()
