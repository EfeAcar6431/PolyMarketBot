import httpx
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from config import settings

GAMMA_BASE = "https://gamma-api.polymarket.com"
SIDE_MAP = {"buy": BUY, "sell": SELL}

SORT_FIELD_MAP = {
    "volume_24hr": "volume24hr",
    "volume24hr": "volume24hr",
    "volume": "volume",
    "liquidity": "liquidity",
    "end_date": "endDate",
    "endDate": "endDate",
    "start_date": "startDate",
    "startDate": "startDate",
    "competitive": "competitive",
}


class PolymarketService:
    def __init__(self):
        self._client: ClobClient | None = None

    def _get_client(self) -> ClobClient:
        if self._client is None:
            if not settings.polymarket_private_key:
                raise RuntimeError("POLYMARKET_PRIVATE_KEY not configured")
            self._client = ClobClient(
                "https://clob.polymarket.com",
                key=settings.polymarket_private_key,
                chain_id=settings.polymarket_chain_id,
                signature_type=1,
            )
            self._client.set_api_creds(self._client.create_or_derive_api_creds())
        return self._client

    async def search_markets(
        self,
        query: str = "",
        tag: str = "",
        sort_by: str = "volume24hr",
        limit: int = 20,
        offset: int = 0,
        active: bool = True,
    ) -> list[dict]:
        api_sort = SORT_FIELD_MAP.get(sort_by, sort_by)
        params: dict = {"limit": limit, "offset": offset, "order": api_sort, "ascending": "false"}
        if active:
            params["active"] = "true"
            params["closed"] = "false"
        if tag:
            params["tag_id"] = tag

        if query:
            async with httpx.AsyncClient() as http:
                resp = await http.get(f"{GAMMA_BASE}/public-search", params={"q": query, "limit_per_type": limit})
                resp.raise_for_status()
                data = resp.json()
                return data.get("events", []) or data.get("markets", [])

        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{GAMMA_BASE}/events", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_market(self, condition_id: str) -> dict:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{GAMMA_BASE}/markets/{condition_id}")
            resp.raise_for_status()
            return resp.json()

    async def get_tags(self) -> list[dict]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{GAMMA_BASE}/tags")
            resp.raise_for_status()
            return resp.json()

    async def get_orderbook(self, token_id: str) -> dict:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://clob.polymarket.com/book",
                params={"token_id": token_id},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_price_history(
        self, token_id: str, interval: str = "max", fidelity: int = 100
    ) -> list[dict]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://clob.polymarket.com/prices-history",
                params={"market": token_id, "interval": interval, "fidelity": str(fidelity)},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("history", [])

    async def get_midpoint(self, token_id: str) -> float:
        client = self._get_client()
        return float(client.get_midpoint(token_id))

    async def get_price(self, token_id: str, side: str = "buy") -> float:
        client = self._get_client()
        return float(client.get_price(token_id, side))

    async def place_limit_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> dict:
        client = self._get_client()
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=SIDE_MAP[side.lower()],
        )
        signed = client.create_order(order_args)
        return client.post_order(signed, OrderType.GTC)

    async def place_market_order(self, token_id: str, side: str, size: float) -> dict:
        client = self._get_client()
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=size,
            side=SIDE_MAP[side.lower()],
        )
        signed = client.create_market_order(order_args)
        return client.post_order(signed)

    async def cancel_order(self, order_id: str) -> dict:
        client = self._get_client()
        return client.cancel(order_id)

    async def cancel_all_orders(self) -> dict:
        client = self._get_client()
        return client.cancel_all()

    async def get_positions(self) -> list:
        client = self._get_client()
        try:
            return client.get_positions()
        except Exception:
            return []

    async def get_balance(self) -> float:
        client = self._get_client()
        try:
            bal = client.get_balance()
            return float(bal) if bal else 0.0
        except Exception:
            return 0.0

    async def get_active_orders(self) -> list:
        client = self._get_client()
        try:
            return client.get_orders()
        except Exception:
            return []


polymarket_service = PolymarketService()
