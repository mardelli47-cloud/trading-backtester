"""Webhook-first, paper-only Telegram trading companion.

The controller deliberately keeps Telegram glue separate from risk/order code.
It never constructs an Alpaca live client and all order paths end in the
existing two-click confirmation service.
"""
from __future__ import annotations
import os
import re
import logging
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from backtester.autopilot import Autopilot, AutopilotState
from backtester.broker.base import OrderRequest
from backtester.execution import PaperOrderService
from backtester.http_headers import validate_header_values
from backtester.market_data import MarketDataError, MarketDataService
from backtester.instruments import InstrumentResolver, ProviderRouter, YFinanceProvider, TwelveDataProvider, CATALOG
from .auth import AccessControl
from .confirmation import OrderConfirmations
from .formatting import error_id, safe_error
from .storage import UserStore
from .ui import keyboard, reply_keyboard

COMMANDS = ("start", "menu", "help", "morning", "daily", "midday", "close", "scan", "plan", "upcoming", "account", "positions", "orders", "risk", "signals", "watchlist", "autopilot", "cryptoauto", "pause", "resume", "kill", "journal", "performance", "compact", "detailed", "settings", "buy", "sell", "status", "profit", "trades", "whoami")
HELP = "Trading-App (nur Alpaca Paper Trading): Nutze das Menü oder /help. Keine Gewinnzusage; Signale verwenden nur abgeschlossene Kerzen."
_SYMBOL = re.compile(r"^[A-Z^][A-Z0-9.=\-/^]{0,9}$")
_BUTTON_COMMANDS = {"📊 Analyse": "analyse", "🔎 Scanner": "scan", "⭐ Watchlist": "watchlist", "🌅 Morning": "morning", "💼 Konto": "account", "📈 Positionen": "positions", "🧾 Orders": "orders", "⚙️ Risiko": "risk", "🤖 Autopilot": "autopilot", "₿ Krypto-Pilot": "cryptoauto", "📔 Journal": "journal", "📅 Termine": "upcoming", "⚙️ Einstellungen": "settings", "🔄 Aktualisieren": "account", "❓ Hilfe": "help"}
LOG = logging.getLogger(__name__)

def is_user_allowed(update, allowed_ids: frozenset[int]) -> bool:
    """Authorize every Telegram update exclusively by effective_user.id."""
    user = getattr(update, "effective_user", None)
    return bool(user and isinstance(getattr(user, "id", None), int) and user.id in allowed_ids)

@dataclass
class Dialog:
    action: str
    expires_at: datetime
    symbol: str = ""
    side: str = ""


class TelegramPaperController:
    def __init__(self, service: PaperOrderService, allowed_ids: frozenset[int], watchlist: tuple[str, ...] = (), autopilot: Autopilot | None = None, store: UserStore | None = None, market_data: MarketDataService | None = None, provider_router: ProviderRouter | None = None, autopilot_runner=None, crypto_autopilot=None, crypto_runner=None, clock: Callable[[], datetime] | None = None):
        self.service, self.access, self.confirmations = service, AccessControl(allowed_ids), OrderConfirmations()
        self._prices: dict[str, Decimal] = {}; self.paused = False; self.autopilot = autopilot or Autopilot(service)
        self.store = store; self.watchlist = self._validate_watchlist(watchlist); self.dialogs: dict[int, Dialog] = {}; self.market_data = market_data
        self.autopilot_runner = autopilot_runner; self.resolver = InstrumentResolver(); self.provider_router = provider_router or ProviderRouter(alpaca_stock=market_data, global_provider=TwelveDataProvider(), yfinance_provider=YFinanceProvider())
        self.crypto_autopilot, self.crypto_runner = crypto_autopilot, crypto_runner
        self._clock = clock or (lambda: datetime.now(timezone.utc))
    def authorize(self, user_id: int) -> bool: return self.access.allowed_now(user_id)
    def kill(self) -> None: self.service.risk.kill_switch = True
    def pause(self) -> None: self.paused = True
    def resume(self) -> None: self.paused = False
    @staticmethod
    def normalize_symbol(text: str) -> str | None:
        value = text.strip().upper()
        if value == "EURUSD": value = "EUR/USD"
        return value if _SYMBOL.fullmatch(value) else None
    def resolve_instrument(self, text: str):
        return self.resolver.resolve(text)
    def instrument_choices(self, text: str):
        return self.resolver.search(text)
    def is_analysis_only(self, symbol: str) -> bool:
        return any(item.canonical_symbol == symbol or item.provider_symbol == symbol for item in CATALOG.values())
    def validate_symbol(self, text: str) -> str | None:
        symbol = self.normalize_symbol(text)
        if not symbol: return None
        instrument = self.resolver.resolve(symbol)
        if instrument: return instrument.canonical_symbol
        # Alpaca validation when supported by the configured adapter.  Mock and
        # legacy adapters retain regex validation for deterministic tests.
        if self.market_data is not None:
            return symbol if self.market_data.validate_symbol(symbol) else None
        client = getattr(self.service.broker, "client", None)
        if client is not None:
            try:
                asset = client.get_asset(symbol)
                if not getattr(asset, "tradable", False): return None
            except Exception: return None
        return symbol
    def begin_dialog(self, user_id: int, action: str, symbol: str = "", side: str = "") -> None:
        self.dialogs[user_id] = Dialog(action, datetime.now(timezone.utc) + timedelta(minutes=5), symbol, side)
    def consume_dialog(self, user_id: int, text: str) -> tuple[str, str] | None:
        dialog = self.dialogs.get(user_id)
        if not dialog or datetime.now(timezone.utc) >= dialog.expires_at:
            self.dialogs.pop(user_id, None); return None
        if dialog.action in {"analyse", "watchlist_add"}:
            symbol = self.validate_symbol(text); self.dialogs.pop(user_id, None)
            return (dialog.action, symbol or "")
        return None
    def user_watchlist(self, user_id: int) -> tuple[str, ...]: return self.store.watchlist(user_id) if self.store else self.watchlist
    def add_watchlist(self, user_id: int, symbol: str) -> None:
        if self.store: self.store.add_symbol(user_id, symbol)
        else: self.watchlist = tuple(dict.fromkeys((*self.watchlist, symbol)))
    def remove_watchlist(self, user_id: int, symbol: str) -> None:
        if self.store: self.store.remove_symbol(user_id, symbol)
        else: self.watchlist = tuple(s for s in self.watchlist if s != symbol)
    def clear_watchlist(self, user_id: int) -> None:
        if self.store: self.store.clear_watchlist(user_id)
        else: self.watchlist = ()
    def propose(self, user_id: int, request: OrderRequest, price: Decimal) -> str:
        if not self.authorize(user_id): raise PermissionError("Nicht autorisiert.")
        if self.is_analysis_only(request.symbol): raise ValueError("Nur Analyse – nicht über Alpaca Paper handelbar.")
        if self.paused or self.service.risk.kill_switch: raise ValueError("Neue Orders sind gestoppt.")
        token = self.confirmations.create(request, price, user_id); self._prices[token] = price; return token
    def confirm(self, user_id: int, token: str):
        if not self.authorize(user_id): raise PermissionError("Nicht autorisiert.")
        request = self.confirmations.confirm(token, user_id)
        if request is None: return None
        price = self._prices.pop(token, None)
        if price is None: raise ValueError("Bestätigung abgelaufen.")
        return self.service.submit(request, price, now=self._clock())
    @staticmethod
    def _validate_watchlist(symbols):
        cleaned = tuple(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if any(not _SYMBOL.fullmatch(s) for s in cleaned): raise ValueError("Watchlist enthält ein ungültiges Symbol.")
        return cleaned
    def analysis_message(self, symbol: str, detailed: bool = True) -> str:
        instrument = self.resolver.resolve(symbol)
        if instrument:
            return self.international_analysis_message(instrument, detailed)
        heading = f"📊 Analyse: {symbol}\n"
        if self.market_data is None:
            return heading + "Marktdaten sind in diesem Worker derzeit nicht verfügbar; daher werden weder Kurs noch Score erfunden.\nFazit: Aktuell kein Trade ohne aktuelle, abgeschlossene Kurskerzen.\n⚠️ PAPER TRADING – KEIN ECHTGELD"
        try:
            daily = self.market_data.get_daily_bars(symbol, 101)
            price = self.market_data.get_latest_price(symbol)
            close = daily["close"].astype(float)
            high, low = daily["high"].astype(float), daily["low"].astype(float)
            trend = "aufwärts" if close.iloc[-1] >= close.tail(20).mean() else "abwärts"
            momentum = (close.iloc[-1] / close.iloc[-10] - 1) * 100 if len(close) >= 10 else 0
            atr = (high - low).tail(14).mean()
            support, resistance = low.tail(20).min(), high.tail(20).max()
            intraday_note = ""
            try:
                intra = self.market_data.get_intraday_bars(symbol, "15Min", 101)
                rel_volume = intra["volume"].tail(20).mean() / intra["volume"].tail(100).mean() if len(intra) >= 20 else 0
            except MarketDataError:
                rel_volume = None; intraday_note = "\nIntraday: vorübergehend nicht verfügbar; Tagesanalyse bleibt gültig."
            score = min(100, max(0, round(50 + (10 if trend == "aufwärts" else -10) + momentum * 3)))
            trigger, stop = resistance * 1.001, support
            target = trigger + 2 * max(trigger - stop, atr)
            return (heading + f"Kurs: ${price:.2f}\nTrend: {trend}\nMomentum (10T): {momentum:+.2f}%\n"
                    + (f"Relatives Volumen: {rel_volume:.2f}\n" if rel_volume is not None else "")
                    + f"ATR (14T): ${atr:.2f}\nUnterstützung: ${support:.2f}\nWiderstand: ${resistance:.2f}\nSetup-Score: {score}/100\nEinstiegstrigger: ${trigger:.2f}\nStop: ${stop:.2f}\nZiel: ${target:.2f}{intraday_note}\nFazit: Nur nach bestätigtem Signal aus abgeschlossenen Kerzen handeln.\n⚠️ PAPER TRADING – KEIN ECHTGELD")
        except MarketDataError as exc:
            return heading + f"Marktdaten konnten nicht geladen werden: {exc}\nEs werden keine Werte erfunden.\n⚠️ PAPER TRADING – KEIN ECHTGELD"
    def international_analysis_message(self, instrument, detailed: bool = True) -> str:
        provider = self.provider_router.provider_for(instrument)
        heading = f"📊 Analyse: {instrument.name} – {instrument.exchange} – {instrument.display_symbol}\n"
        if provider is None:
            return heading + "Globaler Marktdatenprovider nicht konfiguriert und yfinance-Fallback deaktiviert.\nNur Analyse – nicht über Alpaca Paper handelbar."
        try:
            daily = provider.get_daily_bars(instrument, 101)
            close, high, low = daily.bars["close"].astype(float), daily.bars["high"].astype(float), daily.bars["low"].astype(float)
            price=float(close.iloc[-1]); trend="aufwärts" if price >= close.tail(20).mean() else "abwärts"; momentum=(price/close.iloc[-10]-1)*100 if len(close)>=10 else 0
            support,resistance=float(low.tail(20).min()),float(high.tail(20).max()); atr=float((high-low).tail(14).mean())
            score=max(0,min(100,round(50+(15 if trend == "aufwärts" else -15)+momentum*3))) if len(close)>=30 else 0
            delay="verzögert" if daily.delayed else "Echtzeit"; quality="hoch" if len(close)>=100 else "mittel" if len(close)>=30 else "niedrig"
            subtype_note="📊 Future-Referenz – kein Spotpreis und kein direktes Alpaca-Paper-Instrument.\n" if instrument.asset_class == "future_reference" else ""
            index_note="Ein Index ist ein Analyseinstrument. Er wird nicht direkt als Alpaca-Paper-Order gehandelt.\n" if instrument.asset_class == "index" else ""
            return heading + f"Markt: {instrument.exchange} | {instrument.currency} | {instrument.timezone}\nDatenquelle: {daily.provider} | Datenzeitpunkt: {daily.timestamp.isoformat()} | {delay}\nKurs: {price:.4f} | Trend: {trend} | Momentum: {momentum:+.2f}%\nATR: {atr:.4f} | Unterstützung: {support:.4f} | Widerstand: {resistance:.4f}\nSetup-Score: {score}/100 (keine Gewinnwahrscheinlichkeit)\nTrigger: {resistance*1.001:.4f} | Stop: {support:.4f} | Ziel: {resistance+2*atr:.4f}\nDatenqualität: {quality}\n{subtype_note}{index_note}analysis_only=true | Paper-handelbar: nein\nNur Analyse – nicht über Alpaca Paper handelbar."
        except Exception as exc:
            return heading + f"Marktdaten konnten nicht geladen werden: {exc}\nEs werden keine Werte erfunden.\nNur Analyse – nicht über Alpaca Paper handelbar."
    def _scan_message(self, title: str, report: dict, *, crypto: bool = False) -> str:
        state = report.get("state", "unbekannt")
        if report.get("state_blocked"):
            notice = "Pilot ist deaktiviert. Starte ihn zweimal mit /cryptoauto start." if crypto and state == "DISABLED" else report.get("message", "Pilot ist nicht gestartet.")
            details = ", ".join(f"{symbol}: state_blocked" for symbol in report.get("checked", ())) or "–"
            return f"{title}\nZustand: {state}\n{notice}\nDetails: {details}"
        details = []
        for symbol in report.get("checked", ()):
            outcome = report.get("outcomes", {}).get(symbol, "rejected")
            reason = report.get(outcome, {}).get(symbol, "") if isinstance(report.get(outcome), dict) else ""
            details.append(f"{symbol}: {outcome}" + (f" ({reason})" if reason else ""))
        return f"{title}\nZustand: {state}\nGeprüft: {len(report.get('checked', []))}\nAkzeptiert: {len(report.get('accepted', []))}\nAbgelehnt: {len(report.get('rejected', {}))}\nDetails: " + ("; ".join(details) or "–")

    def command_message(self, command: str, args: tuple[str, ...] = (), user_id: int = 0) -> str:
        broker = self.service.broker
        if command == "cryptoauto":
            if not self.crypto_autopilot: raise ValueError("Krypto-Pilot ist nicht konfiguriert.")
            action=args[0].lower() if args else "status"; c=self.crypto_autopilot
            if action in {"status","last","performance","shadow"}: return c.status() + ("\n"+self.crypto_runner.status() if self.crypto_runner else "")
            if action in {"start","shadow"}: return c.start()
            if action == "scan":
                if not self.crypto_runner: raise ValueError("Krypto-Runner fehlt.")
                r=self.crypto_runner.run_cycle(); return self._scan_message("₿ Krypto-Scan", r, crypto=True)
            if action == "paper": return c.activate_paper()
            if action == "pause": c.state=type(c.state).PAUSED
            elif action in {"stop","off"}: c.state=type(c.state).DISABLED
            elif action == "kill": c.state=type(c.state).EMERGENCY_STOP
            elif action == "resume": c.state=type(c.state).SHADOW
            else: raise ValueError("Unbekannter Krypto-Pilot-Befehl.")
            c.save(); return c.status()
        if command == "autopilot":
            action = args[0].lower() if args else "status"
            if action in {"status", "report", "config"}:
                return self.autopilot.status() + ("\n" + self.autopilot_runner.status() if self.autopilot_runner else "") + f"\nPause: {'aktiv' if self.paused else 'inaktiv'}; Kill Switch: {'aktiv' if self.service.risk.kill_switch else 'inaktiv'}"
            if action in {"start", "on"}: return self.autopilot.start()
            if action == "scan":
                if not self.autopilot_runner: raise ValueError("Runner nicht konfiguriert.")
                report = self.autopilot_runner.run_cycle(); return self._scan_message("Autopilot-Scan", report)
            if action == "last": return self.autopilot_runner.status() if self.autopilot_runner else "Kein Runner konfiguriert."
            if action == "shadow": return f"Shadow-Trades: offen {len(self.autopilot.open_plans)}, abgeschlossen {self.autopilot.shadow_closed}."
            if action == "paper": return self.autopilot.activate_paper()
            if action in {"stop", "off"}: self.autopilot.transition(AutopilotState.DISABLED); return "Autopilot deaktiviert; keine neuen Trades."
            if action == "kill": self.autopilot.emergency(); return "Kill Switch aktiviert."
            if action == "pause": self.autopilot.transition(AutopilotState.PAUSED); return "Autopilot pausiert; keine neuen Trades."
            if action == "resume":
                if self.autopilot.state in {AutopilotState.RISK_LOCKED, AutopilotState.EMERGENCY_STOP}: raise ValueError("Manuelle Sicherheitsprüfung erforderlich.")
                self.autopilot.transition(AutopilotState.SHADOW); return "Autopilot im sicheren Shadow-Modus fortgesetzt."
            raise ValueError("Unbekannter Autopilot-Befehl.")
        if command == "morning":
            symbols = self.user_watchlist(user_id) or ("AAPL",)
            if self.market_data is None:
                return "🌅 Morning Briefing\nMarkt- und Ereignisdaten sind nicht verfügbar; es werden keine Nachrichten erfunden."
            return "🌅 Morning Briefing\n\n" + "\n\n".join(self.analysis_message(s, False) for s in symbols)
        if command == "daily": return "📅 Tagesplan\nKeine verifizierten Marktdaten verfügbar. Watchlist: " + (", ".join(self.user_watchlist(user_id)) or "leer")
        if command == "midday": return "🕛 Midday-Update\nKeine verifizierten Änderungen seit Handelsstart verfügbar."
        if command == "close": return "🌙 Tagesrückblick\nPaper-Trades und Regelverstöße werden erst mit persistiertem Journal ausgewertet."
        if command == "upcoming": return "📅 Termine (nächste 7 Tage)\nExterne Earnings-, Wirtschafts- und Fed-Datenquelle ist nicht konfiguriert; es werden keine Ereignisse erfunden."
        if command == "scan":
            symbols = self.user_watchlist(user_id)
            return "🔎 Scanner\n" + ("\n\n".join(self.analysis_message(s, False) for s in symbols) if symbols else "Watchlist ist leer.")
        if command == "plan":
            symbol = self.validate_symbol(args[0]) if args else None
            return self.analysis_message(symbol, True) if symbol else "Bitte nutze /plan SYMBOL. Das Symbol konnte nicht gefunden werden."
        if command == "journal": return "📔 Journal\nNoch keine persistenten Trade-Journal-Einträge vorhanden."
        if command == "settings": return "⚙️ Einstellungen\nNutze /compact oder /detailed für die Anzeigeansicht."
        if command in {"profit", "performance", "trades"}: return "📈 Performance\nNoch keine vollständig berechneten abgeschlossenen Paper-Trades."
        if command == "status": return f"Analysemodus: {'pausiert' if self.paused else 'aktiv'}. Kill Switch: {'aktiv' if self.service.risk.kill_switch else 'inaktiv'}.\n⚠️ PAPER TRADING – KEIN ECHTGELD"
        if command == "signals": return "Signale werden nur aus abgeschlossenen Balken berechnet. Watchlist: " + (", ".join(self.user_watchlist(user_id)) or "keine") + "."
        if command == "watchlist":
            if args and args[0] in {"add", "remove", "clear", "scan"}:
                action = args[0]
                if action == "clear": self.clear_watchlist(user_id); return "Watchlist geleert."
                if action == "scan": return "Watchlist-Scan benötigt aktuelle abgeschlossene Marktdaten; keine Kandidaten ohne Datenquelle."
                symbol = self.validate_symbol(args[1]) if len(args) > 1 else None
                if not symbol: return "Bitte nutze /watchlist " + action + " SYMBOL. Das Symbol konnte nicht gefunden werden."
                if action == "add": self.add_watchlist(user_id, symbol); return f"{symbol} zur Watchlist hinzugefügt."
                self.remove_watchlist(user_id, symbol); return f"{symbol} aus der Watchlist entfernt."
            if args:
                symbols = self._validate_watchlist(tuple(item for arg in args for item in arg.split(",")))
                if self.store:
                    self.clear_watchlist(user_id)
                    for symbol in symbols: self.add_watchlist(user_id, symbol)
                else: self.watchlist = symbols
            return "Watchlist: " + (", ".join(self.user_watchlist(user_id)) or "leer")
        if command in {"compact", "detailed"}:
            if self.store: self.store.set_view_mode(user_id, command)
            return f"Ansicht auf {command} gesetzt."
        if command == "risk":
            s = self.service.risk.settings
            return f"Risikolimits\nRisiko/Trade: {s.max_risk_per_trade_pct}%\nMax. Positionsgröße: {s.max_position_qty}\nMax. offene Positionen: {s.max_open_positions}\nMax. Tagesverlust: {s.max_daily_loss_pct}%\nKill Switch: {'aktiv' if self.service.risk.kill_switch else 'inaktiv'}\nPause: {'aktiv' if self.paused else 'inaktiv'}\nAutopilot: {self.autopilot.state.value}"
        if broker is None: raise RuntimeError("Kein Paper-Broker konfiguriert.")
        if command == "account":
            a = broker.get_account(); return f"Paper-Konto\nEquity: {a.equity}\nKaufkraft: {a.buying_power}\nCash: {a.cash}"
        if command == "positions":
            p = broker.list_positions(); return "Offene Positionen: keine." if not p else "Offene Positionen:\n" + "\n".join(f"{x.symbol}: {x.qty} | Marktwert {x.market_value}" for x in p)
        if command == "orders":
            orders = broker.list_orders(False); return "Orders: keine." if not orders else "Orders:\n" + "\n".join(f"{o.symbol} {o.side} {o.qty} | {o.order_type} | {o.status.value}" for o in orders)
        raise ValueError("Unbekannter Befehl.")

def confirmation_keyboard(token: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("Bestätigen", callback_data=f"cf:{token}"), InlineKeyboardButton("Ablehnen", callback_data=f"rj:{token}")], [InlineKeyboardButton("Kill Switch", callback_data="kill")]])

def build_application(controller: TelegramPaperController, token: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
    async def reply(message, text, **kwargs):
        # Test doubles and older integrations may not accept Telegram kwargs.
        try: await message.reply_text(text, **kwargs)
        except TypeError: await message.reply_text(text)
    def authorized_only(handler):
        @wraps(handler)
        async def wrapped(update, context, *args, **kwargs):
            query = getattr(update, "callback_query", None)
            if query is not None:
                await query.answer()
            if not is_user_allowed(update, controller.access.allowed):
                LOG.info("telegram_authorization allowed=false user_suffix=%s", str(getattr(getattr(update, "effective_user", None), "id", ""))[-3:])
                if query is not None: await query.edit_message_text("⛔ Zugriff verweigert.")
                elif getattr(update, "effective_message", None): await reply(update.effective_message, "⛔ Zugriff verweigert.")
                return
            return await handler(update, context, *args, **kwargs)
        return wrapped
    def update_type(update: Update) -> str:
        return "callback_query" if getattr(update, "callback_query", None) is not None else "message"

    async def guarded(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str, args: tuple[str, ...] = ()):
        user, message = update.effective_user, update.effective_message
        if command in {"start", "menu"}: await reply(message, "Willkommen. Wähle eine Funktion:", reply_markup=reply_keyboard()); return
        if command == "help": await reply(message, HELP, reply_markup=reply_keyboard()); return
        if command == "whoami":
            chat = getattr(update, "effective_chat", None)
            await reply(message, f"Telegram User ID: {user.id}\nTelegram Chat ID: {getattr(chat, 'id', '–')}\nChat-Typ: {getattr(chat, 'type', '–')}\nAutorisiert: ja")
            return
        if command == "pause": controller.pause(); await reply(message, "Analyse-Benachrichtigungen pausiert."); return
        if command == "resume": controller.resume(); await reply(message, "Benachrichtigungen fortgesetzt; Orders bleiben bestätigungspflichtig."); return
        if command == "kill": controller.kill(); await reply(message, "Kill Switch aktiviert. Neue Paper-Orders sind gesperrt."); return
        if command == "buy" or command == "sell": await reply(message, "Paper-Order-Workflow: wähle zuerst ein Symbol in einer Analyse; jede Order benötigt zwei Bestätigungen."); return
        try:
            # MessageHandler updates do not populate ``context.args``.  Keep
            # this boundary defensive as well, so every caller can pass None
            # without turning a reply-keyboard action into a TypeError.
            text = controller.command_message(command, tuple(args or ()), user.id)
            kind = {"watchlist":"watchlist", "autopilot":"autopilot", "cryptoauto":"cryptoautopilot", "account":"account", "scan":"scanner"}.get(command)
            await reply(message, text, reply_markup=keyboard(kind) if kind else None)
        except Exception as exc:
            incident_id = error_id()
            LOG.exception("telegram_handler_failed action=%s update_type=%s error_id=%s", command, update_type(update), incident_id)
            await reply(message, safe_error(exc, incident_id))
    @authorized_only
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user, message = update.effective_user, update.effective_message
        text = (message.text or "").strip()
        if text in _BUTTON_COMMANDS:
            command = _BUTTON_COMMANDS[text]
            if command == "analyse":
                controller.begin_dialog(user.id, "analyse")
                choices = [[InlineKeyboardButton(s, callback_data=f"an:{s}") for s in ("AAPL", "NVDA", "TSLA")], [InlineKeyboardButton("TSEM", callback_data="an:TSEM"), InlineKeyboardButton("SPY", callback_data="an:SPY")], [InlineKeyboardButton("Eigenes Symbol eingeben", callback_data="an:custom"), InlineKeyboardButton("Abbrechen", callback_data="cancel")]]
                await reply(message, "Welches Symbol möchtest du analysieren?", reply_markup=InlineKeyboardMarkup(choices)); return
            await guarded(update, context, command, ()); return
        consumed = controller.consume_dialog(user.id, text)
        if consumed:
            action, symbol = consumed
            if not symbol: await reply(message, "Das Symbol konnte nicht gefunden werden."); return
            if action == "watchlist_add": controller.add_watchlist(user.id, symbol); await reply(message, f"{symbol} zur Watchlist hinzugefügt.", reply_markup=keyboard("watchlist")); return
            await reply(message, controller.analysis_message(symbol, controller.store.view_mode(user.id) != "compact" if controller.store else True), reply_markup=keyboard("analysis", symbol, controller.is_analysis_only(symbol))); return
        symbol = controller.validate_symbol(text)
        if symbol: await reply(message, controller.analysis_message(symbol, True), reply_markup=keyboard("analysis", symbol, controller.is_analysis_only(symbol)))
    @authorized_only
    async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data or ""; user_id = query.from_user.id
        try:
            if data == "menu": await query.message.reply_text("Hauptmenü:", reply_markup=reply_keyboard()); return
            if data == "cancel": controller.dialogs.pop(user_id, None); await query.edit_message_text("Abgebrochen."); return
            if data == "kill": controller.kill(); await query.edit_message_text("Kill Switch aktiviert."); return
            action, value = data.split(":", 1)
            if action in {"cf", "rj"}:
                if action == "rj": controller.confirmations.reject(value, user_id); await query.edit_message_text("Order abgelehnt."); return
                order = controller.confirm(user_id, value); await query.edit_message_text("Erste Bestätigung gespeichert. Bitte erneut bestätigen." if order is None else f"Paper-Order {order.status.value} übermittelt."); return
            if action == "an":
                if value == "custom": controller.begin_dialog(user_id, "analyse"); await query.edit_message_text("Bitte gib ein Börsensymbol ein."); return
                symbol = controller.validate_symbol(value)
                await query.edit_message_text(controller.analysis_message(symbol, True), reply_markup=keyboard("analysis", symbol, controller.is_analysis_only(symbol))) if symbol else await query.edit_message_text("Das Symbol konnte nicht gefunden werden."); return
            if action == "wa":
                if value == "add": controller.begin_dialog(user_id, "watchlist_add"); await query.edit_message_text("Bitte gib ein Börsensymbol ein."); return
                if value == "clear": controller.clear_watchlist(user_id); await query.edit_message_text("Watchlist geleert.", reply_markup=keyboard("watchlist")); return
                if value == "remove": await query.edit_message_text("Bitte nutze /watchlist remove SYMBOL."); return
                symbol = controller.validate_symbol(value)
                if symbol: controller.add_watchlist(user_id, symbol); await query.edit_message_text(f"{symbol} zur Watchlist hinzugefügt.")
                return
            if action == "ap":
                mapping = {"on":"start", "off":"stop", "pause":"pause", "resume":"resume", "status":"status", "scan":"scan", "last":"last", "shadow":"shadow", "paper":"paper", "kill":"kill"}
                await query.edit_message_text(controller.command_message("autopilot", (mapping[value],), user_id), reply_markup=keyboard("autopilot")); return
            if action == "ca":
                mapping = {"start":"start", "off":"stop", "pause":"pause", "status":"status", "scan":"scan", "paper":"paper", "kill":"kill"}
                await query.edit_message_text(controller.command_message("cryptoauto", (mapping[value],), user_id), reply_markup=keyboard("cryptoautopilot")); return
            if action == "cmd": await query.edit_message_text(controller.command_message(value, (), user_id), reply_markup=keyboard("account") if value == "account" else None); return
            if action in {"pl", "sc", "ob", "os"}: await query.edit_message_text("Diese Funktion benötigt aktuelle, abgeschlossene Marktdaten bzw. den geführten Paper-Order-Workflow und ist sicher nicht automatisch ausführbar."); return
            await query.edit_message_text("Dieser Button ist abgelaufen oder ungültig.")
        except (ValueError, KeyError): await query.edit_message_text("Dieser Button ist abgelaufen oder ungültig.")
        except Exception as exc:
            incident_id = error_id()
            LOG.exception("telegram_handler_failed action=%s update_type=%s error_id=%s", data or "callback", update_type(update), incident_id)
            await query.edit_message_text(safe_error(exc, incident_id))
    async def _post_init(application):
        if controller.autopilot_runner: await controller.autopilot_runner.start()
        if controller.crypto_runner: await controller.crypto_runner.start()
    async def _post_shutdown(application):
        if controller.autopilot_runner: await controller.autopilot_runner.stop()
        if controller.crypto_runner: await controller.crypto_runner.stop()
    app = Application.builder().token(token).post_init(_post_init).post_shutdown(_post_shutdown).build()
    for command in COMMANDS:
        @authorized_only
        async def handler(update, context, registered_command=command):
            args = tuple(getattr(context, "args", None) or ())
            await guarded(update, context, registered_command, args)
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callback)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)); return app

def run_worker(controller: TelegramPaperController, token: str, webhook_url: str = "", webhook_secret: str = "", local_polling: bool = False) -> None:
    if webhook_url:
        if webhook_secret: validate_header_values({"X-Telegram-Bot-Api-Secret-Token": (webhook_secret, "TELEGRAM_WEBHOOK_SECRET")})
        port = int(os.environ["PORT"]); build_application(controller, token).run_webhook(listen="0.0.0.0", port=port, url_path="telegram", webhook_url=f"{webhook_url}/telegram", secret_token=webhook_secret or None)
    elif local_polling: build_application(controller, token).run_polling()
    else: raise ValueError("Produktiv ist TELEGRAM_WEBHOOK_URL erforderlich; Polling nur mit --local-polling.")
