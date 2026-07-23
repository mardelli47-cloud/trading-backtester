"""Webhook-first Telegram control plane. It cannot create live Alpaca orders."""
from __future__ import annotations
import os
import re
from decimal import Decimal
from backtester.broker.base import OrderRequest
from backtester.execution import PaperOrderService
from backtester.autopilot import Autopilot, AutopilotState
from backtester.http_headers import validate_header_values
from .auth import AccessControl
from .confirmation import OrderConfirmations
from .formatting import safe_error

COMMANDS = ("start", "help", "status", "signals", "positions", "orders", "account", "risk", "pause", "resume", "kill", "watchlist", "autopilot", "profit", "performance", "trades", "morning", "close")
HELP = "Verfügbar: " + ", ".join("/" + c for c in COMMANDS) + "\n⚠️ PAPER TRADING – KEIN ECHTGELD"
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")

class TelegramPaperController:
    def __init__(self, service: PaperOrderService, allowed_ids: frozenset[int], watchlist: tuple[str, ...] = (), autopilot: Autopilot|None = None):
        self.service=service; self.access=AccessControl(allowed_ids); self.confirmations=OrderConfirmations(); self._prices: dict[str, Decimal] = {}; self.paused=False
        self.watchlist = self._validate_watchlist(watchlist)
        self.autopilot = autopilot or Autopilot(service)
    def authorize(self, user_id: int) -> bool: return self.access.allowed_now(user_id)
    def kill(self) -> None: self.service.risk.kill_switch=True
    def pause(self) -> None: self.paused=True
    def resume(self) -> None: self.paused=False
    def propose(self, user_id: int, request: OrderRequest, price: Decimal) -> str:
        if not self.authorize(user_id): raise PermissionError("Nicht autorisiert.")
        if self.paused or self.service.risk.kill_switch: raise ValueError("Neue Orders sind gestoppt.")
        token = self.confirmations.create(request, price, user_id)
        self._prices[token] = price
        return token
    def confirm(self, user_id: int, token: str):
        if not self.authorize(user_id): raise PermissionError("Nicht autorisiert.")
        request=self.confirmations.confirm(token,user_id)
        if request is None: return None
        price = self._prices.pop(token, None)
        if price is None: raise ValueError("Bestätigung abgelaufen.")
        return self.service.submit(request, price)
    @staticmethod
    def _validate_watchlist(symbols: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        cleaned = tuple(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        if any(not _SYMBOL.fullmatch(symbol) for symbol in cleaned):
            raise ValueError("Watchlist enthält ein ungültiges Symbol.")
        return cleaned
    def command_message(self, command: str, args: tuple[str, ...] = ()) -> str:
        """Return the command-specific, secret-free status message.

        Data is read only from the configured paper broker; this method cannot
        submit, cancel, or otherwise alter an order.
        """
        broker = self.service.broker
        if command == "autopilot":
            action = args[0].lower() if args else "status"
            if action in {"status", "report", "config"}: return self.autopilot.status()
            if action == "start": return self.autopilot.start()
            if action == "stop": self.autopilot.transition(AutopilotState.PAUSED); return "Neue Einstiege gestoppt; bestehende Schutzpläne bleiben aktiv."
            if action == "pause": self.autopilot.transition(AutopilotState.PAUSED); return "Autopilot pausiert; keine neuen Trades."
            if action == "resume":
                if self.autopilot.state in {AutopilotState.RISK_LOCKED, AutopilotState.EMERGENCY_STOP}: raise ValueError("Manuelle Sicherheitsprüfung nach Risk Lock/Kill Switch erforderlich.")
                self.autopilot.transition(AutopilotState.SHADOW); return "Autopilot im sicheren Shadow-Modus fortgesetzt."
            if action == "shadow": self.autopilot.transition(AutopilotState.SHADOW); return "Shadow-Modus aktiv: keine Alpaca-Order wird gesendet."
            if action == "paper": self.autopilot.transition(AutopilotState.PAPER_ACTIVE); return "Ausschließlich Alpaca-Paper-Modus aktiviert."
            if action == "emergency":
                self.autopilot.emergency(); return "Kill Switch aktiv. Neue Orders gesperrt. Offene Positionen werden nicht automatisch ohne explizite Schließbestätigung geschlossen."
            raise ValueError("Unbekannter Autopilot-Befehl.")
        if command in {"profit", "performance", "trades", "morning", "close"}:
            return self.autopilot.status() + "\nTagesbericht: Noch keine vollständig berechneten Paper-Trades."
        if command == "status":
            state = "pausiert" if self.paused else "aktiv"
            kill = "aktiv" if self.service.risk.kill_switch else "inaktiv"
            return f"Analysemodus: {state}. Kill Switch: {kill}.\n⚠️ PAPER TRADING – KEIN ECHTGELD"
        if command == "signals":
            symbols = ", ".join(self.watchlist) or "keine"
            return f"Signale werden nur aus abgeschlossenen Balken berechnet. Watchlist: {symbols}.\nDerzeit liegen keine aktuellen Signale vor."
        if command == "watchlist":
            if args:
                self.watchlist = self._validate_watchlist(tuple(item for arg in args for item in arg.split(",")))
            return "Watchlist: " + (", ".join(self.watchlist) if self.watchlist else "leer")
        if broker is None:
            raise RuntimeError("Kein Paper-Broker konfiguriert.")
        if command == "account":
            account = broker.get_account()
            return f"Paper-Konto\nEquity: {account.equity}\nKaufkraft: {account.buying_power}\nCash: {account.cash}"
        if command == "positions":
            positions = broker.list_positions()
            return "Offene Positionen: keine." if not positions else "Offene Positionen:\n" + "\n".join(
                f"{p.symbol}: {p.qty} | Marktwert {p.market_value} | Unrealisiert {p.unrealized_pl}" for p in positions
            )
        if command == "orders":
            orders = broker.list_orders(False)
            return "Orders: keine." if not orders else "Orders:\n" + "\n".join(
                f"{o.symbol} {o.side} {o.qty} | {o.order_type} | {o.status.value}" for o in orders
            )
        if command == "risk":
            settings = self.service.risk.settings
            return (
                "Risikolimits\n"
                f"Max. Positionsgröße: {settings.max_position_qty}\n"
                f"Max. offene Positionen: {settings.max_open_positions}\n"
                f"Max. Tagesverlust: {settings.max_daily_loss_pct}%\n"
                f"Kill Switch: {'aktiv' if self.service.risk.kill_switch else 'inaktiv'}"
            )
        raise ValueError("Unbekannter Befehl.")

def confirmation_keyboard(token: str):
    """Inline buttons attached to a proposed Paper order notification."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("Bestätigen", callback_data=f"confirm:{token}"), InlineKeyboardButton("Ablehnen", callback_data=f"reject:{token}")], [InlineKeyboardButton("Kill Switch", callback_data=f"kill:{token}")]])

def build_application(controller: TelegramPaperController, token: str):
    """Create handlers lazily so importing the backtester does not require Telegram."""
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
    async def guarded(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str):
        user=update.effective_user
        if not user or not controller.authorize(user.id):
            if update.effective_message: await update.effective_message.reply_text("Zugriff verweigert.")
            return
        if command == "kill": controller.kill(); await update.effective_message.reply_text("Kill Switch aktiviert. Neue Paper-Orders sind gesperrt.")
        elif command == "pause": controller.pause(); await update.effective_message.reply_text("Analyse-Benachrichtigungen pausiert.")
        elif command == "resume": controller.resume(); await update.effective_message.reply_text("Benachrichtigungen fortgesetzt; Orders bleiben bestätigungspflichtig.")
        elif command == "help" or command == "start": await update.effective_message.reply_text(HELP)
        else:
            try:
                await update.effective_message.reply_text(controller.command_message(command, tuple(context.args)))
            except Exception as exc:
                await update.effective_message.reply_text(safe_error(exc))
    async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query=update.callback_query; await query.answer()
        if not query.from_user or not controller.authorize(query.from_user.id): await query.edit_message_text("Zugriff verweigert."); return
        action, token = query.data.split(":", 1)
        if action == "kill": controller.kill(); await query.edit_message_text("Kill Switch aktiviert. Neue Orders sind gesperrt."); return
        if action == "reject": await query.edit_message_text("Order abgelehnt."); controller.confirmations.reject(token, query.from_user.id); return
        try:
            order=controller.confirm(query.from_user.id, token)
            await query.edit_message_text("Erste Bestätigung gespeichert. Bitte erneut bestätigen." if order is None else f"Paper-Order {order.status.value} übermittelt.")
        except Exception as exc: await query.edit_message_text(safe_error(exc))
    app=Application.builder().token(token).build()
    # Bind each command while registering it.  A single handler that reparses
    # message text loses the command suffix used in group chats (e.g.
    # ``/account@my_bot``) and used to send every read-only command to its
    # fallback status response.
    for command in COMMANDS:
        async def handler(update, context, registered_command=command):
            await guarded(update, context, registered_command)
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callback)); return app

def run_worker(controller: TelegramPaperController, token: str, webhook_url: str = "", webhook_secret: str = "", local_polling: bool = False) -> None:
    if webhook_url:
        # Telegram sends this header with webhook requests when a secret is set.
        # Validate it before constructing or starting the Telegram application.
        if webhook_secret:
            validate_header_values({
                "X-Telegram-Bot-Api-Secret-Token": (webhook_secret, "TELEGRAM_WEBHOOK_SECRET"),
            })
        app=build_application(controller, token)
        # Render Web Services publish the listener that uses their injected PORT.
        # PTB calls the bind-address argument `listen`; it is the server host.
        host = "0.0.0.0"
        port = int(os.environ["PORT"])
        app.run_webhook(listen=host, port=port, url_path="telegram", webhook_url=f"{webhook_url}/telegram", secret_token=webhook_secret or None)
    elif local_polling:
        app=build_application(controller, token)
        app.run_polling()
    else:
        raise ValueError("Produktiv ist TELEGRAM_WEBHOOK_URL erforderlich; Polling nur mit --local-polling.")
