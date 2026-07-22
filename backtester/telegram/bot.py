"""Webhook-first Telegram control plane. It cannot create live Alpaca orders."""
from __future__ import annotations
import os
from decimal import Decimal
from backtester.broker.base import OrderRequest
from backtester.execution import PaperOrderService
from .auth import AccessControl
from .confirmation import OrderConfirmations
from .formatting import safe_error

COMMANDS = ("start", "help", "status", "signals", "positions", "orders", "account", "risk", "pause", "resume", "kill", "watchlist")
HELP = "Verfügbar: " + ", ".join("/" + c for c in COMMANDS) + "\n⚠️ PAPER TRADING – KEIN ECHTGELD"

class TelegramPaperController:
    def __init__(self, service: PaperOrderService, allowed_ids: frozenset[int]):
        self.service=service; self.access=AccessControl(allowed_ids); self.confirmations=OrderConfirmations(); self._prices: dict[str, Decimal] = {}; self.paused=False
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

def confirmation_keyboard(token: str):
    """Inline buttons attached to a proposed Paper order notification."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton("Bestätigen", callback_data=f"confirm:{token}"), InlineKeyboardButton("Ablehnen", callback_data=f"reject:{token}")], [InlineKeyboardButton("Kill Switch", callback_data=f"kill:{token}")]])

def build_application(controller: TelegramPaperController, token: str):
    """Create handlers lazily so importing the backtester does not require Telegram."""
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
    async def guarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user=update.effective_user
        if not user or not controller.authorize(user.id):
            if update.effective_message: await update.effective_message.reply_text("Zugriff verweigert.")
            return
        command=(update.effective_message.text or "").split()[0][1:]
        if command == "kill": controller.kill(); await update.effective_message.reply_text("Kill Switch aktiviert. Neue Paper-Orders sind gesperrt.")
        elif command == "pause": controller.pause(); await update.effective_message.reply_text("Analyse-Benachrichtigungen pausiert.")
        elif command == "resume": controller.resume(); await update.effective_message.reply_text("Benachrichtigungen fortgesetzt; Orders bleiben bestätigungspflichtig.")
        elif command == "help" or command == "start": await update.effective_message.reply_text(HELP)
        else: await update.effective_message.reply_text("Analysemodus: keine Order ohne zweifache Bestätigung. " + HELP)
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
    for command in COMMANDS: app.add_handler(CommandHandler(command, guarded))
    app.add_handler(CallbackQueryHandler(callback)); return app

def run_worker(controller: TelegramPaperController, token: str, webhook_url: str = "", webhook_secret: str = "", local_polling: bool = False) -> None:
    app=build_application(controller, token)
    if webhook_url:
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "8080")), url_path="telegram", webhook_url=f"{webhook_url}/telegram", secret_token=webhook_secret or None)
    elif local_polling:
        app.run_polling()
    else:
        raise ValueError("Produktiv ist TELEGRAM_WEBHOOK_URL erforderlich; Polling nur mit --local-polling.")
