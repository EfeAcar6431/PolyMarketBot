import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI

from config import settings
from services.polymarket import polymarket_service

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = [
    "basketball_nba",
    "americanfootball_nfl",
    "soccer_epl",
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "icehockey_nhl",
    "baseball_mlb",
    "mma_mixed_martial_arts",
]

SPORTS_FEE = 0.0075

MATCHER_SYSTEM = """You are a sports event matching engine. Given a list of Polymarket prediction markets and a list of sportsbook events, match them.

Rules:
- Only match events that clearly refer to the SAME game/match/event
- Use team names, dates, and sport type to match
- Return ONLY valid JSON: an array of objects with "poly_index" (0-based index in the Polymarket list) and "odds_index" (0-based index in the sportsbook list)
- If a Polymarket market has no matching sportsbook event, skip it
- Be conservative: only match when confident"""


@dataclass
class OddsCache:
    data: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0


@dataclass
class Discrepancy:
    poly_title: str
    poly_condition_id: str
    poly_token_id: str
    poly_price: float
    sportsbook_implied: float
    edge: float
    net_edge: float
    side: str
    bookmaker: str
    sport: str
    orderbook_flow_agrees: bool
    orderbook_bid_depth: float
    orderbook_ask_depth: float


class OddsComparator:
    def __init__(self):
        self._cache: dict[str, OddsCache] = {}
        self._client: AsyncOpenAI | None = None

    def _get_llm(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY not configured")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def fetch_sportsbook_odds(self, sport_key: str, cache_minutes: int = 120) -> list[dict]:
        if not settings.odds_api_key:
            return []

        cached = self._cache.get(sport_key)
        if cached and (time.time() - cached.fetched_at) < cache_minutes * 60:
            return cached.data

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                    params={
                        "apiKey": settings.odds_api_key,
                        "regions": "us",
                        "markets": "h2h",
                        "oddsFormat": "decimal",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self._cache[sport_key] = OddsCache(data=data, fetched_at=time.time())
                remaining = resp.headers.get("x-requests-remaining", "?")
                logger.info("Odds API: fetched %s (%d events, %s credits left)", sport_key, len(data), remaining)
                return data
        except Exception as e:
            logger.warning("Odds API fetch failed for %s: %s", sport_key, e)
            return cached.data if cached else []

    async def get_available_sports(self) -> list[dict]:
        if not settings.odds_api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{ODDS_API_BASE}/sports",
                    params={"apiKey": settings.odds_api_key},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("Odds API sports list failed: %s", e)
            return []

    @staticmethod
    def implied_probability(decimal_odds: float) -> float:
        if decimal_odds <= 1.0:
            return 1.0
        return 1.0 / decimal_odds

    @staticmethod
    def remove_vig(probs: list[float]) -> list[float]:
        total = sum(probs)
        if total <= 0:
            return probs
        return [p / total for p in probs]

    @staticmethod
    def consensus_implied(event: dict) -> dict[str, float]:
        """Average implied probability across all bookmakers for each outcome."""
        outcome_probs: dict[str, list[float]] = {}
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                raw_probs = []
                outcomes_list = []
                for outcome in market.get("outcomes", []):
                    name = outcome["name"]
                    prob = OddsComparator.implied_probability(outcome["price"])
                    raw_probs.append(prob)
                    outcomes_list.append(name)
                fair_probs = OddsComparator.remove_vig(raw_probs)
                for name, fp in zip(outcomes_list, fair_probs):
                    outcome_probs.setdefault(name, []).append(fp)

        result = {}
        for name, probs in outcome_probs.items():
            result[name] = sum(probs) / len(probs)
        return result

    async def fetch_polymarket_sports(self, limit: int = 30) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={
                        "limit": limit,
                        "active": "true",
                        "closed": "false",
                        "order": "volume24hr",
                        "ascending": "false",
                        "tag": "sports",
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("Polymarket sports fetch failed: %s", e)
            return []

    async def match_events(
        self, poly_markets: list[dict], odds_events: list[dict]
    ) -> list[tuple[int, int]]:
        """Use LLM to match Polymarket markets to sportsbook events. Returns (poly_idx, odds_idx) pairs."""
        if not poly_markets or not odds_events:
            return []

        poly_summaries = []
        for i, m in enumerate(poly_markets):
            title = m.get("title", m.get("question", ""))
            poly_summaries.append(f"{i}: {title}")

        odds_summaries = []
        for i, e in enumerate(odds_events):
            home = e.get("home_team", "")
            away = e.get("away_team", "")
            sport = e.get("sport_title", "")
            start = e.get("commence_time", "")
            odds_summaries.append(f"{i}: {away} @ {home} ({sport}, {start})")

        user_msg = (
            f"Polymarket markets:\n"
            + "\n".join(poly_summaries)
            + f"\n\nSportsbook events:\n"
            + "\n".join(odds_summaries)
        )

        try:
            llm = self._get_llm()
            resp = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": MATCHER_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=1000,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            matches = json.loads(raw)
            return [(m["poly_index"], m["odds_index"]) for m in matches]
        except Exception as e:
            logger.warning("LLM event matching failed: %s", e)
            return []

    async def check_orderbook_flow(self, token_id: str) -> tuple[float, float]:
        """Returns (bid_depth_dollars, ask_depth_dollars) for top 5 levels."""
        if not token_id:
            return 0.0, 0.0
        try:
            book = await polymarket_service.get_orderbook(token_id)
            bid_total = 0.0
            for order in (book.get("bids") or [])[:5]:
                bid_total += float(order.get("price", 0)) * float(order.get("size", 0))
            ask_total = 0.0
            for order in (book.get("asks") or [])[:5]:
                ask_total += float(order.get("price", 0)) * float(order.get("size", 0))
            return round(bid_total, 2), round(ask_total, 2)
        except Exception as e:
            logger.warning("Orderbook flow check failed: %s", e)
            return 0.0, 0.0

    def _extract_poly_price_and_token(self, market: dict) -> tuple[float, str]:
        """Extract YES price and token_id from a Polymarket market dict."""
        tokens = market.get("tokens", [])
        price = 0.5
        token_id = ""
        if tokens:
            for t in tokens:
                if t.get("outcome", "").lower() == "yes":
                    price = float(t.get("price", 0.5))
                    token_id = t.get("token_id", "")
                    break
            if not token_id and tokens:
                price = float(tokens[0].get("price", 0.5))
                token_id = tokens[0].get("token_id", "")

        if price == 0.5 and market.get("outcomePrices"):
            try:
                prices = market["outcomePrices"]
                if isinstance(prices, str):
                    prices = json.loads(prices)
                price = float(prices[0])
            except Exception:
                pass

        return price, token_id

    async def find_discrepancies(self, config: dict) -> list[Discrepancy]:
        """Main pipeline: fetch odds, fetch Polymarket, match, compare, check flow."""
        cache_minutes = int(config.get("odds_cache_minutes", 120))
        min_edge = float(config.get("odds_min_edge", 0.03))

        all_odds_events: list[dict] = []
        for sport_key in SPORT_KEYS:
            events = await self.fetch_sportsbook_odds(sport_key, cache_minutes=cache_minutes)
            for e in events:
                e["_sport_key"] = sport_key
            all_odds_events.extend(events)

        if not all_odds_events:
            return []

        poly_events = await self.fetch_polymarket_sports(limit=30)
        flat_markets: list[dict] = []
        for event in poly_events:
            if "markets" in event:
                for m in event["markets"]:
                    m["_event_title"] = event.get("title", "")
                    flat_markets.append(m)
            else:
                flat_markets.append(event)

        if not flat_markets:
            return []

        matches = await self.match_events(flat_markets, all_odds_events)
        if not matches:
            return []

        discrepancies: list[Discrepancy] = []
        for poly_idx, odds_idx in matches:
            if poly_idx >= len(flat_markets) or odds_idx >= len(all_odds_events):
                continue

            pm = flat_markets[poly_idx]
            oe = all_odds_events[odds_idx]
            poly_price, token_id = self._extract_poly_price_and_token(pm)
            consensus = self.consensus_implied(oe)
            if not consensus:
                continue

            home = oe.get("home_team", "")
            away = oe.get("away_team", "")
            title = pm.get("question", pm.get("title", pm.get("_event_title", "")))

            best_match_team = home
            best_prob = consensus.get(home, 0.5)
            for team, prob in consensus.items():
                if abs(prob - poly_price) > abs(best_prob - poly_price):
                    continue
                best_match_team = team
                best_prob = prob

            edge = best_prob - poly_price
            net_edge = abs(edge) - SPORTS_FEE
            if net_edge < min_edge:
                continue

            side = "buy" if edge > 0 else "sell"

            bid_depth, ask_depth = await self.check_orderbook_flow(token_id)
            if side == "buy":
                flow_agrees = bid_depth > ask_depth * 1.2
            else:
                flow_agrees = ask_depth > bid_depth * 1.2

            discrepancies.append(Discrepancy(
                poly_title=title,
                poly_condition_id=pm.get("conditionId", pm.get("condition_id", "")),
                poly_token_id=token_id,
                poly_price=poly_price,
                sportsbook_implied=best_prob,
                edge=edge,
                net_edge=net_edge,
                side=side,
                bookmaker=f"consensus ({len(oe.get('bookmakers', []))} books)",
                sport=oe.get("sport_title", oe.get("_sport_key", "")),
                orderbook_flow_agrees=flow_agrees,
                orderbook_bid_depth=bid_depth,
                orderbook_ask_depth=ask_depth,
            ))

        discrepancies.sort(key=lambda d: d.net_edge, reverse=True)
        return discrepancies

    async def get_cached_discrepancies(self, config: dict) -> list[dict]:
        discs = await self.find_discrepancies(config)
        return [
            {
                "title": d.poly_title,
                "condition_id": d.poly_condition_id,
                "token_id": d.poly_token_id,
                "poly_price": d.poly_price,
                "sportsbook_implied": round(d.sportsbook_implied, 4),
                "edge": round(d.edge, 4),
                "net_edge": round(d.net_edge, 4),
                "side": d.side,
                "bookmaker": d.bookmaker,
                "sport": d.sport,
                "flow_agrees": d.orderbook_flow_agrees,
                "bid_depth": d.orderbook_bid_depth,
                "ask_depth": d.orderbook_ask_depth,
            }
            for d in discs
        ]


odds_comparator = OddsComparator()
