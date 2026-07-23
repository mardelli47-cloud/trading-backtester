"""Webhook-first, paper-only Telegram trading companion.

The controller deliberately keeps Telegram glue separate from risk/order code.
It never constructs an Alpaca live client and all order paths end in the
existing two-click confirmation service.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backtester.autopilot import Autopilot, AutopilotState
from backtester.broker.base import OrderRequest
from backtester.execution import PaperOrderService
from backtester.http_headers import validate_header_values
from .auth import AccessControl
from .confirmation import OrderConfirmations
from .formatting import safe_error
from .storage import UserStore
from .ui import keyboard, reply_keyboard

COMMANDS = ("start", "menu", "help", "morning", "daily", "midday", "close", "scan", "plan", "upcoming", "account", "positions", "orders", "risk", "signals", "watchlist", "autopilot", "pause", "resume", "kill", "journal", "performance", "compact", "detailed", "buy", "sell", "status", "profit", "trades")
HELP = "Trading-App (nur Alpaca Paper Trading): Nutze das Menü oder /help. Keine Gewinnzusage; Signale verwenden nur abgeschlossene Kerzen."
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_BUTTON_COMMANDS = {"📊 Analyse": "analyse", "🔎 Scanner": "scan", "⭐ Watchlist": "watchlist", "🌅 Morning": "morning", "💼 Konto": "account", "📈 Positionen": "positions", "🧾 Orders": "orders", "⚙️ Risiko": "risk", "🤖 Autopilot": "autopilot", "📔 Journal": "journal", "📅 Termine": "upcoming", "⚙️ Einstellungen": "settings", "🔄 Aktualisieren": "account", "❓ Hilfe": "help"}

@dataclass
class Dialog:
    action: str
    expires_at: datetime
    symbol: str = ""
    side: str = ""


class TelegramPaperController:
    def __init__(self, service: PaperOrderService, allowed_ids: frozenset[int], watchlist: tuple[str, ...] = (), autopilot: Autopilot | None = None, store: UserStore | None = None):
        self.service, self.access, self.confirmations = service, AccessControl(allowed_ids), OrderConfirmations()
        self._prices: dict[str, Decimal] = {}; self.paused = False; self.autopilot = autopilot or Autopilot(service)
        self.store = store; self.watchlist = self._validate_watchlist(watchlist); self.dialogs: dict[int, Dialog] = {}
    def authorize(self, user_id: int) -> bool: return self.access.allowed_now(user_id)
    def kill(self) -> None: self.service.risk.kill_switch = True
    def pause(self) -> None: self.paused = True
    def resume(self) -> None: self.paused = False
    @staticmethod
    def normalize_symbol(text: str) -> str | None:
        value = text.strip().upper()
        return value if _SYMBOL.fullmatch(value) else None
    def validate_symbol(self, text: str) -> str | None:
        symbol = self.normalize_symbol(text)
        if not symbol: return None
        # Alpaca validation when supported by the configured adapter.  Mock and
        # legacy adapters retain regex validation for deterministic tests.
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
        if self.paused or self.service.risk.kill_switch: raise ValueError("Neue Orders sind gestoppt.")
        token = self.confirmations.create(request, price, user_id); self._prices[token] = price; return token
    def confirm(self, user_id: int, token: str):
        if not self.authorize(user_id): raise PermissionError("Nicht autorisiert.")
        request = self.confirmations.confirm(token, user_id)
        if request is None: return None
        price = self._prices.pop(token, None)
        if price is None: raise ValueError("Bestätigung abgelaufen.")
        return self.service.submit(request, price)
    @staticmethod
    def _validate_watchlist(symbols):
        cleaned = tuple(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if any(not _SYMBOL.fullmatch(s) for s in cleaned): raise ValueError("Watchlist enthält ein ungültiges Symbol.")
        return cleaned
    def analysis_message(self, symbol: str, detailed: bool = True) -> str:
        # Do not fabricate market data. Dedicated market-data integrations can
        # replace this deterministic, honest unavailable response.
        heading = f"📊 Analyse: {symbol}\n"
        if detailed: heading += "Marktdaten sind in diesem Worker derzeit nicht verfügbar; daher werden weder Kurs noch Score erfunden.\n"
        return heading + "Fazit: Aktuell kein Trade ohne aktuelle, abgeschlossene Kurskerzen.\n⚠️ PAPER TRADING – KEIN ECHTGELD"
    def command_message(self, command: str, args: tuple[str, ...] = (), user_id: int = 0) -> str:
        broker = self.service.broker
        if command == "autopilot":
            action = args[0].lower() if args else "status"
            if action in {"status", "report", "config"}:
                return self.autopilot.status() + f"\nPause: {'aktiv' if self.paused else 'inaktiv'}; Kill Switch: {'aktiv' if self.service.risk.kill_switch else 'inaktiv'}"
            if action in {"start", "on"}: return self.autopilot.start()
            if action in {"stop", "off"}: self.autopilot.transition(AutopilotState.PAUSED); return "Autopilot deaktiviert; keine neuen Trades."
            if action == "pause": self.autopilot.transition(AutopilotState.PAUSED); return "Autopilot pausiert; keine neuen Trades."
            if action == "resume":
                if self.autopilot.state in {AutopilotState.RISK_LOCKED, AutopilotState.EMERGENCY_STOP}: raise ValueError("Manuelle Sicherheitsprüfung erforderlich.")
                self.autopilot.transition(AutopilotState.SHADOW); return "Autopilot im sicheren Shadow-Modus fortgesetzt."
            raise ValueError("Unbekannter Autopilot-Befehl.")
        if command == "morning": return "🌅 Morning Briefing\nMarkt- und Ereignisdaten sind ohne konfigurierte Marktdatenquelle nicht verfügbar. Es werden keine Kurse, Termine oder Nachrichten erfunden."
        if command == "daily": return "📅 Tagesplan\nKeine verifizierten Marktdaten verfügbar. Watchlist: " + (", ".join(self.user_watchlist(user_id)) or "leer")
        if command == "midday": return "🕛 Midday-Update\nKeine verifizierten Änderungen seit Handelsstart verfügbar."
        if command == "close": return "🌙 Tagesrückblick\nPaper-Trades und Regelverstöße werden erst mit persistiertem Journal ausgewertet."
        if command == "upcoming": return "📅 Termine (nächste 7 Tage)\nExterne Earnings-, Wirtschafts- und Fed-Datenquelle ist nicht konfiguriert; es werden keine Ereignisse erfunden."
        if command == "scan": return "🔎 Scanner\nManuelle Scans benötigen aktuelle abgeschlossene Marktdaten. Ohne Datenquelle keine Kandidaten."
        if command == "plan":
            symbol = self.validate_symbol(args[0]) if args else None
            return self.analysis_message(symbol, True) if symbol else "Bitte nutze /plan SYMBOL. Das Symbol konnte nicht gefunden werden."
        if command == "journal": return "📔 Journal\nNoch keine persistenten Trade-Journal-Einträge vorhanden."
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
    async def guarded(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str):
        user, message = update.effective_user, update.effective_message
        if not user or not controller.authorize(user.id): await reply(message, "Zugriff verweigert."); return
        if command in {"start", "menu"}: await reply(message, "Willkommen. Wähle eine Funktion:", reply_markup=reply_keyboard()); return
        if command == "help": await reply(message, HELP, reply_markup=reply_keyboard()); return
        if command == "pause": controller.pause(); await reply(message, "Analyse-Benachrichtigungen pausiert."); return
        if command == "resume": controller.resume(); await reply(message, "Benachrichtigungen fortgesetzt; Orders bleiben bestätigungspflichtig."); return
        if command == "kill": controller.kill(); await reply(message, "Kill Switch aktiviert. Neue Paper-Orders sind gesperrt."); return
        if command == "buy" or command == "sell": await reply(message, "Paper-Order-Workflow: wähle zuerst ein Symbol in einer Analyse; jede Order benötigt zwei Bestätigungen."); return
        try:
            text = controller.command_message(command, tuple(context.args), user.id)
            kind = {"watchlist":"watchlist", "autopilot":"autopilot", "account":"account", "scan":"scanner"}.get(command)
            await reply(message, text, reply_markup=keyboard(kind) if kind else None)
        except Exception as exc: await reply(message, safe_error(exc))
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user, message = update.effective_user, update.effective_message
        if not user or not controller.authorize(user.id): await reply(message, "Zugriff verweigert."); return
        text = (message.text or "").strip()
        if text in _BUTTON_COMMANDS:
            command = _BUTTON_COMMANDS[text]
            if command == "analyse":
                controller.begin_dialog(user.id, "analyse")
                choices = [[InlineKeyboardButton(s, callback_data=f"an:{s}") for s in ("AAPL", "NVDA", "TSLA")], [InlineKeyboardButton("TSEM", callback_data="an:TSEM"), InlineKeyboardButton("SPY", callback_data="an:SPY")], [InlineKeyboardButton("Eigenes Symbol eingeben", callback_data="an:custom"), InlineKeyboardButton("Abbrechen", callback_data="cancel")]]
                await reply(message, "Welches Symbol möchtest du analysieren?", reply_markup=InlineKeyboardMarkup(choices)); return
            await guarded(update, context, command); return
        consumed = controller.consume_dialog(user.id, text)
        if consumed:
            action, symbol = consumed
            if not symbol: await reply(message, "Das Symbol konnte nicht gefunden werden."); return
            if action == "watchlist_add": controller.add_watchlist(user.id, symbol); await reply(message, f"{symbol} zur Watchlist hinzugefügt.", reply_markup=keyboard("watchlist")); return
            await reply(message, controller.analysis_message(symbol, controller.store.view_mode(user.id) != "compact" if controller.store else True), reply_markup=keyboard("analysis", symbol)); return
        symbol = controller.validate_symbol(text)
        if symbol: await reply(message, controller.analysis_message(symbol, True), reply_markup=keyboard("analysis", symbol))
    async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query; await query.answer()
        if not query.from_user or not controller.authorize(query.from_user.id): await query.edit_message_text("Zugriff verweigert."); return
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
                await query.edit_message_text(controller.analysis_message(symbol, True), reply_markup=keyboard("analysis", symbol)) if symbol else await query.edit_message_text("Das Symbol konnte nicht gefunden werden."); return
            if action == "wa":
                if value == "add": controller.begin_dialog(user_id, "watchlist_add"); await query.edit_message_text("Bitte gib ein Börsensymbol ein."); return
                if value == "clear": controller.clear_watchlist(user_id); await query.edit_message_text("Watchlist geleert.", reply_markup=keyboard("watchlist")); return
                if value == "remove": await query.edit_message_text("Bitte nutze /watchlist remove SYMBOL."); return
                symbol = controller.validate_symbol(value)
                if symbol: controller.add_watchlist(user_id, symbol); await query.edit_message_text(f"{symbol} zur Watchlist hinzugefügt.")
                return
            if action == "ap":
                mapping = {"on":"start", "off":"stop", "pause":"pause", "resume":"resume", "status":"status"}
                await query.edit_message_text(controller.command_message("autopilot", (mapping[value],), user_id), reply_markup=keyboard("autopilot")); return
            if action == "cmd": await query.edit_message_text(controller.command_message(value, (), user_id), reply_markup=keyboard("account") if value == "account" else None); return
            if action in {"pl", "sc", "ob", "os"}: await query.edit_message_text("Diese Funktion benötigt aktuelle, abgeschlossene Marktdaten bzw. den geführten Paper-Order-Workflow und ist sicher nicht automatisch ausführbar."); return
            await query.edit_message_text("Dieser Button ist abgelaufen oder ungültig.")
        except (ValueError, KeyError): await query.edit_message_text("Dieser Button ist abgelaufen oder ungültig.")
        except Exception as exc: await query.edit_message_text(safe_error(exc))
    app = Application.builder().token(token).build()
    for command in COMMANDS:
        async def handler(update, context, registered_command=command): await guarded(update, context, registered_command)
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callback)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)); return app

def run_worker(controller: TelegramPaperController, token: str, webhook_url: str = "", webhook_secret: str = "", local_polling: bool = False) -> None:
    if webhook_url:
        if webhook_secret: validate_header_values({"X-Telegram-Bot-Api-Secret-Token": (webhook_secret, "TELEGRAM_WEBHOOK_SECRET")})
        port = int(os.environ["PORT"]); build_application(controller, token).run_webhook(listen="0.0.0.0", port=port, url_path="telegram", webhook_url=f"{webhook_url}/telegram", secret_token=webhook_secret or None)
    elif local_polling: build_application(controller, token).run_polling()
    else: raise ValueError("Produktiv ist TELEGRAM_WEBHOOK_URL erforderlich; Polling nur mit --local-polling.")
