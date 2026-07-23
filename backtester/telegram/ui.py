"""Telegram menus with short, stable callback data."""
from __future__ import annotations

MAIN_MENU = (("📊 Analyse", "🔎 Scanner"), ("⭐ Watchlist", "🌅 Morning"), ("💼 Konto", "📈 Positionen"), ("🧾 Orders", "⚙️ Risiko"), ("🤖 Autopilot", "📔 Journal"), ("📅 Termine", "⚙️ Einstellungen"), ("🔄 Aktualisieren", "❓ Hilfe"))

def reply_keyboard():
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True, is_persistent=True)

def keyboard(kind: str, symbol: str = "", analysis_only: bool = False):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    sets = {
        "analysis": (("⭐ Watchlist hinzufügen", f"wa:{symbol}"), ("📋 Handelsplan", f"pl:{symbol}"), ("🔄 Aktualisieren", f"an:{symbol}"), ("📈 Paper Buy", f"ob:{symbol}"), ("📉 Paper Sell", f"os:{symbol}"), ("◀️ Hauptmenü", "menu")),
        "watchlist": (("➕ Hinzufügen", "wa:add"), ("➖ Entfernen", "wa:remove"), ("🔎 Watchlist scannen", "sc:watch"), ("🗑 Leeren", "wa:clear"), ("◀️ Hauptmenü", "menu")),
        "autopilot": (("🟢 Aktivieren", "ap:on"), ("🔴 Deaktivieren", "ap:off"), ("⏸ Pausieren", "ap:pause"), ("▶️ Fortsetzen", "ap:resume"), ("⚙️ Einstellungen", "settings"), ("📊 Status", "ap:status"), ("◀️ Hauptmenü", "menu")),
        "account": (("📈 Positionen", "cmd:positions"), ("🧾 Orders", "cmd:orders"), ("📊 Tages-P&L", "cmd:performance"), ("⚙️ Risiko", "cmd:risk"), ("🔄 Aktualisieren", "cmd:account")),
        "scanner": (("🔥 Top Setups", "sc:top"), ("📈 Long Setups", "sc:long"), ("📉 Short Setups", "sc:short"), ("🚀 Breakouts", "sc:breakout"), ("↩️ Pullbacks", "sc:pullback"), ("⚡ Momentum", "sc:momentum"), ("⭐ Watchlist Scan", "sc:watch"), ("◀️ Hauptmenü", "menu")),
    }
    rows = sets[kind]
    if kind == "analysis" and analysis_only:
        rows = tuple(row for row in rows if not row[1].startswith(("ob:", "os:")))
    return M([[B(text, callback_data=data)] for text, data in rows])
