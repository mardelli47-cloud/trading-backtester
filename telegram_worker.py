"""Start the secure Telegram worker (webhook in production)."""
from __future__ import annotations
import argparse
import logging
from decimal import Decimal
from backtester.broker import AlpacaPaperBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram.bot import TelegramPaperController, run_worker
from backtester.telegram.config import TelegramSettings
from backtester.telegram.storage import UserStore
from backtester.market_data import MarketDataService

LOG = logging.getLogger(__name__)

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--local-polling", action="store_true", help="Nur lokale Entwicklung; Produktion verwendet Webhook."); args=parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings=TelegramSettings.from_env()
    LOG.info("telegram_allowed_ids_present=%s count=%d", bool(settings.allowed_user_ids), len(settings.allowed_user_ids))
    broker=AlpacaPaperBroker(settings.alpaca_api_key, settings.alpaca_secret_key, paper=settings.alpaca_paper)
    account=broker.get_account()
    market_data = MarketDataService(settings.alpaca_api_key, settings.alpaca_secret_key, settings.alpaca_data_feed)
    LOG.info("market_data_initialized provider=alpaca feed=%s health=%s", settings.alpaca_data_feed, market_data.healthcheck())
    controller=TelegramPaperController(PaperOrderService(broker, RiskManager(RiskSettings(), account.equity), paper_enabled=True), settings.allowed_user_ids, store=UserStore(), market_data=market_data)
    run_worker(controller, settings.token, settings.webhook_url, settings.webhook_secret, args.local_polling)
if __name__ == "__main__": main()
