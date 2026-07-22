"""Start the secure Telegram worker (webhook in production)."""
from __future__ import annotations
import argparse
from decimal import Decimal
from backtester.broker import AlpacaPaperBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram.bot import TelegramPaperController, run_worker
from backtester.telegram.config import TelegramSettings

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--local-polling", action="store_true", help="Nur lokale Entwicklung; Produktion verwendet Webhook."); args=parser.parse_args()
    settings=TelegramSettings.from_env()
    broker=AlpacaPaperBroker(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.alpaca_paper)
    account=broker.get_account()
    controller=TelegramPaperController(PaperOrderService(broker, RiskManager(RiskSettings(), account.equity), paper_enabled=True), settings.allowed_user_ids)
    run_worker(controller, settings.token, settings.webhook_url, settings.webhook_secret, args.local_polling)
if __name__ == "__main__": main()
