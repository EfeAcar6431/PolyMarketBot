import asyncio
import logging
import json
from datetime import datetime, timezone

from database import get_config, set_config, log_event, insert_trade
from services.polymarket import polymarket_service
from services.llm_analyzer import llm_analyzer
from services.edge_validator import edge_validator, EdgeValidator
from services.risk_manager import risk_manager
from services.news_fetcher import news_fetcher
from services.sentiment_monitor import sentiment_monitor
from services.market_maker import market_maker
from services.odds_comparator import odds_comparator, SPORTS_FEE
from services.whale_conviction import whale_conviction
from services.live_scalper import live_scalper
from services.market_sniper import market_sniper
from services.position_manager import position_manager

logger = logging.getLogger(__name__)


class WebSocketBroadcaster:
    def __init__(self):
        self.connections: list = []

    async def connect(self, ws):
        self.connections.append(ws)

    def disconnect(self, ws):
        self.connections = [c for c in self.connections if c != ws]

    async def broadcast(self, event: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


broadcaster = WebSocketBroadcaster()


async def _emit(level: str, message: str, metadata: dict | None = None):
    event = {
        "type": "log",
        "level": level,
        "message": message,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await log_event(level, message, metadata)
    await broadcaster.broadcast(event)


class AgentRunner:
    """Manages the main scan loop plus three independent strategy tasks."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        await set_config("agent_status", "running")

        self._task = asyncio.create_task(self._loop())

        config = await get_config()
        if config.get("whale_conviction_enabled", "true").lower() == "true":
            await whale_conviction.start()
        if config.get("scalper_enabled", "false").lower() == "true":
            await live_scalper.start()
        if config.get("sniper_enabled", "false").lower() == "true":
            await market_sniper.start()

        await _emit("info", "Agent started (main loop + strategy tasks)")

    async def stop(self):
        self._running = False
        await set_config("agent_status", "stopped")

        await whale_conviction.stop()
        await live_scalper.stop()
        await market_sniper.stop()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await _emit("info", "Agent stopped (all tasks)")

    async def _loop(self):
        try:
            while self._running:
                config = await get_config()
                interval = int(config.get("scan_interval", 300))
                news_fetcher.clear_cache()
                await self._run_cycle(config)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Agent loop error")
            await _emit("error", f"Agent error: {e}")
            self._running = False
            await set_config("agent_status", "error")

    async def _run_cycle(self, config: dict):
        paper_mode = config.get("paper_mode", "true").lower() == "true"
        mode_label = "[PAPER] " if paper_mode else ""
        await _emit("info", f"{mode_label}Starting scan cycle...")

        min_edge = float(config.get("min_edge_threshold", 0.05))
        max_position = float(config.get("max_position_size", 50.0))

        try:
            balance = await polymarket_service.get_balance()
        except Exception:
            balance = float(config.get("max_total_exposure", 500.0))

        try:
            markets = await polymarket_service.search_markets(sort_by="volume24hr", limit=15)
        except Exception as e:
            await _emit("error", f"{mode_label}Failed to fetch markets: {e}")
            return

        if not markets:
            await _emit("info", f"{mode_label}No markets found")
            return

        flat_markets = []
        for event in markets:
            if "markets" in event:
                for m in event["markets"]:
                    flat_markets.append(m)
            else:
                flat_markets.append(event)

        preferred = [
            m for m in flat_markets
            if EdgeValidator.is_preferred_category(m.get("category", ""))
        ]
        other = [
            m for m in flat_markets
            if not EdgeValidator.is_preferred_category(m.get("category", ""))
        ]
        ordered = preferred + other
        scan_batch = ordered[:8]

        await _emit(
            "info",
            f"{mode_label}Analyzing {len(scan_batch)} markets "
            f"({len(preferred)} preferred-category, {len(other)} other)...",
        )

        try:
            analyses = await llm_analyzer.batch_analyze(scan_batch)
        except Exception as e:
            await _emit("error", f"{mode_label}LLM analysis failed: {e}")
            return

        for a in analyses:
            edge = abs(a.get("edge", 0))
            if edge < min_edge:
                continue
            if a.get("confidence", 0) < 0.3:
                continue

            token_id = a.get("token_id", "")
            if not token_id:
                continue

            market_data = {}
            for m in scan_batch:
                mid = m.get("condition_id", m.get("conditionId", m.get("id", "")))
                if mid == a["market_id"]:
                    market_data = m
                    break

            bankroll = max(balance, float(config.get("max_total_exposure", 500.0)))
            validation = await edge_validator.validate(
                analysis=a,
                market=market_data,
                bankroll=bankroll,
                max_position=max_position,
            )

            if not validation.approved:
                await _emit(
                    "info",
                    f"{mode_label}Skipped '{a['question'][:60]}': {validation.reason}",
                    {"kelly": validation.kelly_fraction, "fee": validation.fee_rate},
                )
                continue

            side = "buy" if a["edge"] > 0 else "sell"
            bet_size = validation.bet_size

            risk = await risk_manager.check_trade(side, bet_size, a["current_price"])
            if not risk.approved:
                await _emit("warning", f"{mode_label}Trade rejected: {risk.reason}", {"market": a["question"]})
                continue

            final_size = risk.adjusted_size
            trade_meta = {
                "market_id": a["market_id"],
                "side": side,
                "size": final_size,
                "price": a["current_price"],
                "edge": round(a["edge"], 4),
                "kelly_fraction": validation.kelly_fraction,
                "fee_rate": validation.fee_rate,
                "depth": validation.available_depth,
                "news_injected": a.get("news_injected", False),
                "paper": paper_mode,
                "strategy": "llm_edge_v2",
            }

            if paper_mode:
                await _emit(
                    "trade",
                    f"[PAPER] Would {side.upper()} ${final_size:.2f} on '{a['question']}' "
                    f"(edge: {a['edge']*100:.1f}%, Kelly: {validation.kelly_fraction:.2%}, fee: {validation.fee_rate*100:.1f}%)",
                    trade_meta,
                )
                await insert_trade(
                    market_id=a["market_id"],
                    market_question=a["question"],
                    token_id=token_id,
                    side=side,
                    price=a["current_price"],
                    size=final_size,
                    status="paper",
                    strategy_reason=a.get("reasoning", ""),
                    order_id="PAPER",
                )
                risk_manager.record_trade()
            else:
                await _emit(
                    "trade",
                    f"Placing LIVE {side.upper()} ${final_size:.2f} on '{a['question']}'",
                    trade_meta,
                )
                try:
                    result = await polymarket_service.place_limit_order(
                        token_id=token_id,
                        side=side,
                        price=a["current_price"],
                        size=final_size,
                    )
                    order_id = result.get("orderID", result.get("id", ""))
                    await insert_trade(
                        market_id=a["market_id"],
                        market_question=a["question"],
                        token_id=token_id,
                        side=side,
                        price=a["current_price"],
                        size=final_size,
                        status="placed",
                        strategy_reason=a.get("reasoning", ""),
                        order_id=order_id,
                    )
                    risk_manager.record_trade()
                    await _emit("info", f"Order placed: {order_id}")
                except Exception as e:
                    await _emit("error", f"Order failed: {e}", {"market": a["question"]})
                    await insert_trade(
                        market_id=a["market_id"],
                        market_question=a["question"],
                        token_id=token_id,
                        side=side,
                        price=a["current_price"],
                        size=final_size,
                        status="failed",
                        strategy_reason=str(e),
                    )

        await _emit("info", f"{mode_label}LLM scan complete, checking odds discrepancies...")
        await self._run_odds_cycle(config, paper_mode, mode_label)

        await _emit("info", f"{mode_label}Checking sentiment signals...")
        await self._run_sentiment_cycle(config, flat_markets, paper_mode, mode_label)

        await self._run_mm_cycle(config, paper_mode, mode_label)

        await _emit("info", f"{mode_label}Running position exit checks...")
        await self._run_exit_checks(config, paper_mode, mode_label)

        await _emit("info", f"{mode_label}Scan cycle complete")

    async def _run_exit_checks(self, config: dict, paper_mode: bool, mode_label: str):
        """Run mechanical exits + periodic LLM re-evaluation."""
        try:
            closed = await position_manager.run_mechanical_exits(paper_mode)
            for c in closed:
                await _emit("info",
                    f"{mode_label}Position closed: {c.get('market_title', '')[:40]} — {c.get('exit_reason', '')}",
                    {"strategy": c.get("strategy", ""), "pnl": c.get("pnl", 0)})
        except Exception as e:
            logger.warning("Mechanical exit check failed: %s", e)

    async def _run_odds_cycle(self, config: dict, paper_mode: bool, mode_label: str):
        odds_enabled = config.get("odds_comparison", "true").lower() == "true"
        if not odds_enabled:
            return

        from config import settings as app_settings
        if not app_settings.odds_api_key:
            return

        try:
            discrepancies = await odds_comparator.find_discrepancies(config)
        except Exception as e:
            logger.warning("Odds comparison failed: %s", e)
            await _emit("warning", f"{mode_label}Odds comparison error: {e}")
            return

        if not discrepancies:
            await _emit("info", f"{mode_label}No sportsbook discrepancies found")
            return

        await _emit("info", f"{mode_label}Found {len(discrepancies)} odds discrepancies")

        kelly_mult = float(config.get("kelly_multiplier_odds", 0.5))
        max_position = float(config.get("max_position_size", 50.0))

        try:
            balance = await polymarket_service.get_balance()
        except Exception:
            balance = float(config.get("max_total_exposure", 500.0))
        bankroll = max(balance, float(config.get("max_total_exposure", 500.0)))

        for disc in discrepancies[:5]:
            confidence = 0.85 if disc.orderbook_flow_agrees else 0.6
            bet_size, kelly = EdgeValidator.kelly_bet(
                true_probability=disc.sportsbook_implied,
                market_price=disc.poly_price,
                confidence=confidence,
                bankroll=bankroll,
                fee_rate=SPORTS_FEE,
                kelly_multiplier=kelly_mult,
            )

            bet_size = min(bet_size, max_position)
            if bet_size < 1.0:
                continue

            risk = await risk_manager.check_trade(disc.side, bet_size, disc.poly_price)
            if not risk.approved:
                await _emit("warning", f"{mode_label}Odds trade rejected: {risk.reason}")
                continue

            final_size = risk.adjusted_size
            flow_label = "flow confirms" if disc.orderbook_flow_agrees else "no flow confirm"
            trade_meta = {
                "market_id": disc.poly_condition_id,
                "side": disc.side,
                "size": final_size,
                "price": disc.poly_price,
                "sportsbook_implied": round(disc.sportsbook_implied, 4),
                "edge": round(disc.edge, 4),
                "net_edge": round(disc.net_edge, 4),
                "kelly": kelly,
                "kelly_multiplier": kelly_mult,
                "flow_agrees": disc.orderbook_flow_agrees,
                "sport": disc.sport,
                "paper": paper_mode,
                "strategy": "odds_discrepancy",
            }

            if paper_mode:
                await _emit(
                    "trade",
                    f"[PAPER] Odds {disc.side.upper()} ${final_size:.2f} on "
                    f"'{disc.poly_title[:50]}' (edge: {disc.net_edge*100:.1f}%, {flow_label})",
                    trade_meta,
                )
                await insert_trade(
                    market_id=disc.poly_condition_id,
                    market_question=disc.poly_title,
                    token_id=disc.poly_token_id,
                    side=disc.side,
                    price=disc.poly_price,
                    size=final_size,
                    status="paper",
                    strategy_reason=f"Odds discrepancy: sportsbook={disc.sportsbook_implied:.2%} vs PM={disc.poly_price:.2%}, {flow_label}",
                    order_id="PAPER-ODDS",
                )
                risk_manager.record_trade()
            else:
                await _emit(
                    "trade",
                    f"LIVE odds {disc.side.upper()} ${final_size:.2f} on '{disc.poly_title[:50]}'",
                    trade_meta,
                )
                try:
                    result = await polymarket_service.place_limit_order(
                        token_id=disc.poly_token_id,
                        side=disc.side,
                        price=disc.poly_price,
                        size=final_size,
                    )
                    order_id = result.get("orderID", result.get("id", ""))
                    await insert_trade(
                        market_id=disc.poly_condition_id,
                        market_question=disc.poly_title,
                        token_id=disc.poly_token_id,
                        side=disc.side,
                        price=disc.poly_price,
                        size=final_size,
                        status="placed",
                        strategy_reason=f"Odds discrepancy: {disc.sport}",
                        order_id=order_id,
                    )
                    risk_manager.record_trade()
                except Exception as e:
                    await _emit("error", f"Odds order failed: {e}")

    async def _run_mm_cycle(self, config: dict, paper_mode: bool, mode_label: str):
        mm_enabled = config.get("market_making", "false").lower() == "true"
        if not mm_enabled:
            return

        await _emit("info", f"{mode_label}Running market-making cycle...")
        try:
            results = await market_maker.run_cycle(config)
            for r in results:
                if "error" in r:
                    await _emit("warning", f"{mode_label}MM error on {r['token_id'][:10]}: {r['error']}")
                else:
                    await _emit(
                        "info",
                        f"{mode_label}MM: {r.get('title','')[:40]} — "
                        f"{r['orders_placed']} orders, spread={r['spread']:.1%}, "
                        f"reward score={r['reward_score']:.1f}",
                    )
        except Exception as e:
            logger.warning("Market-making cycle failed: %s", e)
            await _emit("error", f"{mode_label}MM cycle error: {e}")

    async def _run_sentiment_cycle(
        self, config: dict, flat_markets: list[dict], paper_mode: bool, mode_label: str
    ):
        sentiment_enabled = config.get("sentiment_monitoring", "true").lower() == "true"
        if not sentiment_enabled:
            return

        try:
            alerts = await sentiment_monitor.scan_markets_for_moves(flat_markets)
        except Exception as e:
            logger.warning("Sentiment scan failed: %s", e)
            return

        for alert in alerts:
            await _emit(
                "warning",
                f"{mode_label}Sudden move detected: '{alert.title[:50]}' "
                f"moved {alert.change_pct*100:+.1f}% in {alert.window_seconds//60}m",
                {
                    "condition_id": alert.condition_id,
                    "price_before": alert.price_before,
                    "price_after": alert.price_after,
                    "change_pct": round(alert.change_pct, 4),
                },
            )

            try:
                evaluation = await sentiment_monitor.evaluate_alert(alert, config)
            except Exception as e:
                logger.warning("Sentiment evaluation failed: %s", e)
                await sentiment_monitor.record_alert(alert, f"eval_error: {e}", "none")
                continue

            verdict = "overreaction" if evaluation["is_overreaction"] else "justified"
            if not evaluation["is_overreaction"]:
                await sentiment_monitor.record_alert(alert, verdict, "skip")
                await _emit("info", f"{mode_label}Sentiment: move appears justified, skipping")
                continue

            side = evaluation["side"]
            bet_size = evaluation["bet_size"]
            if bet_size < 1.0:
                await sentiment_monitor.record_alert(alert, verdict, "too_small")
                continue

            risk = await risk_manager.check_trade(side, bet_size, alert.price_after)
            if not risk.approved:
                await sentiment_monitor.record_alert(alert, verdict, f"risk_rejected: {risk.reason}")
                await _emit("warning", f"{mode_label}Sentiment trade rejected: {risk.reason}")
                continue

            final_size = risk.adjusted_size
            trade_meta = {
                "market_id": alert.condition_id,
                "side": side,
                "size": final_size,
                "price": alert.price_after,
                "edge": round(evaluation["edge"], 4),
                "kelly": evaluation["kelly"],
                "move_pct": round(alert.change_pct * 100, 1),
                "paper": paper_mode,
                "strategy": "sentiment_contrarian",
            }

            if paper_mode:
                await _emit(
                    "trade",
                    f"[PAPER] Contrarian {side.upper()} ${final_size:.2f} on "
                    f"'{alert.title[:50]}' (move: {alert.change_pct*100:+.1f}%)",
                    trade_meta,
                )
                await insert_trade(
                    market_id=alert.condition_id,
                    market_question=alert.title,
                    token_id=alert.token_id,
                    side=side,
                    price=alert.price_after,
                    size=final_size,
                    status="paper",
                    strategy_reason=f"Sentiment contrarian: {evaluation['reasoning'][:200]}",
                    order_id="PAPER-SENTIMENT",
                )
                risk_manager.record_trade()
            else:
                await _emit(
                    "trade",
                    f"LIVE contrarian {side.upper()} ${final_size:.2f} on '{alert.title[:50]}'",
                    trade_meta,
                )
                try:
                    result = await polymarket_service.place_limit_order(
                        token_id=alert.token_id,
                        side=side,
                        price=alert.price_after,
                        size=final_size,
                    )
                    order_id = result.get("orderID", result.get("id", ""))
                    await insert_trade(
                        market_id=alert.condition_id,
                        market_question=alert.title,
                        token_id=alert.token_id,
                        side=side,
                        price=alert.price_after,
                        size=final_size,
                        status="placed",
                        strategy_reason=f"Sentiment contrarian",
                        order_id=order_id,
                    )
                    risk_manager.record_trade()
                except Exception as e:
                    await _emit("error", f"Sentiment order failed: {e}")

            await sentiment_monitor.record_alert(alert, verdict, f"{side} ${final_size:.2f}")


agent_runner = AgentRunner()
