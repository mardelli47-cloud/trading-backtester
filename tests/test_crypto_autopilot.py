from datetime import datetime, timezone
from decimal import Decimal
from backtester.crypto_autopilot import CryptoAutopilot, CryptoMarketSnapshot, CryptoState

def asset(): return {"symbol":"BTC/USD","asset_class":"crypto","status":"active","tradable":True,"min_order_size":"0.001","qty_increment":"0.001","price_increment":"0.01"}
def snap(): return CryptoMarketSnapshot("BTC/USD",datetime.now(timezone.utc),Decimal("100"),Decimal("99.9"),Decimal("100.1"),Decimal("2"),Decimal("100"),Decimal("2"),Decimal("99"),True,True,True,False,True,"x")
def test_normalizes_and_validates_assets(tmp_path):
 a=CryptoAutopilot(path=tmp_path/'x'); a.set_assets([asset()]); assert a.normalize('btcusd')=='BTC/USD' and 'BTC/USD' in a.assets
def test_shadow_is_long_only_and_closes_once(tmp_path):
 a=CryptoAutopilot(path=tmp_path/'x'); a.set_assets([asset()]); a.state=CryptoState.SHADOW
 p=a.plan(snap(),Decimal('10000'),Decimal('10000')); assert p and p.qty > 0 and p.qty % Decimal('0.001') == 0
 assert a.open_shadow(p); assert a.close_shadow('BTC/USD',p.target,'target'); assert not a.close_shadow('BTC/USD',p.target,'target'); assert len(a.closed)==1
def test_live_env_blocks_paper(tmp_path,monkeypatch):
 a=CryptoAutopilot(path=tmp_path/'x'); monkeypatch.setenv('ALPACA_PAPER','false')
 try: a.activate_paper()
 except ValueError: pass
 else: assert False
