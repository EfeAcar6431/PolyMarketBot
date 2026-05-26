import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class OrderPlan:
    action: str = "skip"
    token_id: str = ""
    side: str = "buy"
    price: float = 0.0
    size: float = 0.0
    order_type: str = "limit"
    exit_target: float = 0.0
    stop_loss: float = 0.0
    hold_duration: str = "settlement"


@dataclass
class TradingPlan:
    strategy: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    orders: list[OrderPlan] = field(default_factory=list)


PLAN_SCHEMA_DESCRIPTION = """You MUST respond with ONLY valid JSON matching this schema:
{
  "strategy": "<the strategy name you were told>",
  "reasoning": "<your full reasoning in 2-5 sentences>",
  "confidence": <float 0.0-1.0>,
  "orders": [
    {
      "action": "buy" | "sell" | "skip",
      "token_id": "<the token_id for this outcome>",
      "side": "buy" | "sell",
      "price": <float limit price>,
      "size": <float dollar amount>,
      "order_type": "limit" | "market",
      "exit_target": <float price to take profit>,
      "stop_loss": <float price to cut loss>,
      "hold_duration": "settlement" | "2h" | "30m" | "1h" | "4h"
    }
  ]
}
If you decide not to trade, return orders as an empty list with action reasoning."""


def _parse_trading_plan(raw: str, strategy: str) -> TradingPlan:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse agent plan JSON: %s", text[:200])
        return TradingPlan(strategy=strategy, reasoning=f"Parse error: {text[:200]}", confidence=0.0)

    orders = []
    for o in data.get("orders", []):
        if o.get("action", "skip") == "skip":
            continue
        orders.append(OrderPlan(
            action=o.get("action", "skip"),
            token_id=o.get("token_id", ""),
            side=o.get("side", "buy"),
            price=float(o.get("price", 0)),
            size=float(o.get("size", 0)),
            order_type=o.get("order_type", "limit"),
            exit_target=float(o.get("exit_target", 0)),
            stop_loss=float(o.get("stop_loss", 0)),
            hold_duration=o.get("hold_duration", "settlement"),
        ))

    return TradingPlan(
        strategy=data.get("strategy", strategy),
        reasoning=data.get("reasoning", ""),
        confidence=float(data.get("confidence", 0)),
        orders=orders,
    )


class TradingAgent:
    def __init__(self):
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY not configured")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def run(
        self,
        strategy: str,
        system_prompt: str,
        context: dict,
        tools: list[dict],
        tool_handlers: dict,
        max_steps: int = 5,
        timeout: float = 30.0,
    ) -> tuple[TradingPlan, list[dict]]:
        """Run the multi-step agent loop.

        Returns (TradingPlan, reasoning_chain) where reasoning_chain
        is a list of dicts recording every LLM response and tool call
        for the thought log.
        """
        client = self._get_client()
        reasoning_chain: list[dict] = []

        full_system = f"{system_prompt}\n\n{PLAN_SCHEMA_DESCRIPTION}"

        messages: list[dict] = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": json.dumps(context, default=str)},
        ]

        try:
            for step in range(max_steps):
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                        temperature=0.3,
                        max_tokens=1200,
                    ),
                    timeout=timeout,
                )

                msg = resp.choices[0].message

                if msg.tool_calls:
                    messages.append(msg)
                    for tc in msg.tool_calls:
                        fn_name = tc.function.name
                        fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}

                        reasoning_chain.append({
                            "step": step,
                            "type": "tool_call",
                            "tool": fn_name,
                            "args": fn_args,
                        })

                        handler = tool_handlers.get(fn_name)
                        if handler:
                            try:
                                result = await asyncio.wait_for(handler(**fn_args), timeout=10.0)
                            except asyncio.TimeoutError:
                                result = {"error": f"Tool {fn_name} timed out"}
                            except Exception as e:
                                result = {"error": str(e)}
                        else:
                            result = {"error": f"Unknown tool: {fn_name}"}

                        result_str = json.dumps(result, default=str)
                        if len(result_str) > 4000:
                            result_str = result_str[:4000] + "...(truncated)"

                        reasoning_chain.append({
                            "step": step,
                            "type": "tool_result",
                            "tool": fn_name,
                            "result_preview": result_str[:500],
                        })

                        messages.append({
                            "role": "tool",
                            "content": result_str,
                            "tool_call_id": tc.id,
                        })
                else:
                    content = msg.content or ""
                    reasoning_chain.append({
                        "step": step,
                        "type": "final_response",
                        "content": content[:2000],
                    })
                    plan = _parse_trading_plan(content, strategy)
                    return plan, reasoning_chain

        except asyncio.TimeoutError:
            reasoning_chain.append({"type": "error", "message": "Agent timed out"})
            return TradingPlan(strategy=strategy, reasoning="Agent timed out", confidence=0.0), reasoning_chain
        except Exception as e:
            logger.exception("Agent run failed")
            reasoning_chain.append({"type": "error", "message": str(e)})
            return TradingPlan(strategy=strategy, reasoning=f"Error: {e}", confidence=0.0), reasoning_chain

        reasoning_chain.append({"type": "error", "message": "Max steps reached without final plan"})
        return TradingPlan(strategy=strategy, reasoning="Max steps reached", confidence=0.0), reasoning_chain


trading_agent = TradingAgent()
