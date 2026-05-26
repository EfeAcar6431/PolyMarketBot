import json
import logging
from openai import AsyncOpenAI

from config import settings
from services.news_fetcher import news_fetcher

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert prediction market analyst specializing in Polymarket. You estimate the true probability of outcomes by combining base rates, recent news, and market context.

Given a market question, its current price, and recent news headlines, produce a calibrated probability estimate.

Analytical framework:
1. Establish a base rate from historical precedents
2. Update based on the specific news and context provided
3. Check for common biases: favorite-longshot bias, recency bias, availability bias
4. Consider time remaining until resolution and what could change
5. Account for market efficiency — the current price already reflects public information, so only deviate when you have a clear reason

Return ONLY valid JSON with this exact schema:
{
  "estimated_probability": <float 0.0-1.0>,
  "confidence": <float 0.0-1.0 — how certain you are in YOUR estimate vs the market>,
  "reasoning": "<2-3 sentence explanation of why your estimate differs from market price, or why it agrees>"
}"""


class LLMAnalyzer:
    def __init__(self):
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY not configured")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def _fetch_news_context(self, question: str) -> str:
        try:
            headlines = await news_fetcher.fetch_headlines(question, limit=5)
            if not headlines:
                return ""
            lines = "\n".join(f"- {h}" for h in headlines)
            return f"\nRecent news headlines:\n{lines}"
        except Exception as e:
            logger.warning("News fetch failed: %s", e)
            return ""

    async def analyze_market(
        self, question: str, current_price: float, description: str = "",
        inject_news: bool = True,
    ) -> dict:
        client = self._get_client()

        news_block = ""
        if inject_news:
            news_block = await self._fetch_news_context(question)

        user_content = f"""Market Question: {question}
Current Yes Price: {current_price:.4f} (implies {current_price*100:.1f}% probability)
Current No Price: {1 - current_price:.4f}"""

        if description:
            user_content += f"\n\nMarket Description: {description}"
        if news_block:
            user_content += f"\n{news_block}"

        try:
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(raw)
            result["edge"] = result["estimated_probability"] - current_price
            result["news_injected"] = bool(news_block)
            return result
        except Exception as e:
            logger.error("LLM analysis failed: %s", e)
            return {
                "estimated_probability": current_price,
                "confidence": 0.0,
                "reasoning": f"Analysis failed: {e}",
                "edge": 0.0,
                "news_injected": False,
            }

    async def batch_analyze(self, markets: list[dict]) -> list[dict]:
        results = []
        for m in markets:
            tokens = m.get("tokens", [])
            price = 0.5
            if tokens:
                for t in tokens:
                    if t.get("outcome", "").lower() == "yes":
                        price = float(t.get("price", 0.5))
                        break

            if price == 0.5 and m.get("outcomePrices"):
                try:
                    prices = m["outcomePrices"]
                    if isinstance(prices, str):
                        prices = json.loads(prices)
                    price = float(prices[0])
                except Exception:
                    pass

            token_id = ""
            if tokens:
                for t in tokens:
                    if t.get("outcome", "").lower() == "yes":
                        token_id = t.get("token_id", "")
                        break
                if not token_id and tokens:
                    token_id = tokens[0].get("token_id", "")

            analysis = await self.analyze_market(
                question=m.get("question", m.get("title", "")),
                current_price=price,
                description=m.get("description", ""),
            )
            results.append(
                {
                    "market_id": m.get("condition_id", m.get("conditionId", m.get("id", ""))),
                    "question": m.get("question", m.get("title", "")),
                    "current_price": price,
                    "token_id": token_id,
                    "category": (m.get("category", "") or "").lower(),
                    **analysis,
                }
            )
        return results


llm_analyzer = LLMAnalyzer()
