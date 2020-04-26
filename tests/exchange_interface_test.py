from collections import defaultdict

from core.exchange_interface import ExchangeInterface
from core.instrument import Instrument
from core.orders import OrderSide
from core.websocket_client import Channel, Environment
from sortedcontainers import SortedDict as sd


class MockWebsocketClient:
    def __init__(
        self,
        symbols,
        channels=None,
        channel_kwargs=None,
        env=Environment.STAGING,
        api_key=None,
    ):
        self.authenticated = False

        self.symbols = symbols
        self.symbol_details = {s: {} for s in symbols}
        self.channels = channels or Channel.ALL
        self.channel_kwargs = channel_kwargs or {}

        self._api_key = api_key

        # use these dictionaries to store the data we receive
        self.balances = {}
        self.tickers = {}

        self.l2_book = {}
        for symbol in self.symbols:
            self.l2_book[symbol] = {"bids": sd(), "asks": sd()}

        self.candles = defaultdict(list)
        self.market_trades = defaultdict(list)
        self.open_orders = defaultdict(dict)

    def connect(self):
        pass


# TODO be consistent with floor / rounding / ceils


class TestExchangeInterface:
    def test_scale_quantity(self):
        ins_details = {
            "base_currency_scale": 2,
        }
        assert ExchangeInterface._scale_quantity(ins_details, 0.01) == 0.01
        assert ExchangeInterface._scale_quantity(ins_details, 0.011) == 0.01
        # assert ExchangeInterface._scale_quantity(ins_details, 0.0199) == 0.02
        # assert ExchangeInterface._scale_quantity(ins_details, 2.555) == 2.56
        # assert ExchangeInterface._scale_quantity(ins_details, 1222) == 1222

    def test_scale_price(self):
        ins_details = {"min_price_increment": 10, "min_price_increment_scale": 2}
        assert ExchangeInterface._scale_price(ins_details, 1000) == 1000
        assert ExchangeInterface._scale_price(ins_details, 1000.001) == 1000
        assert ExchangeInterface._scale_price(ins_details, 1000.01) == 1000
        assert ExchangeInterface._scale_price(ins_details, 1000.1) == 1000.1
        # assert ExchangeInterface._scale_price(ins_details, 1001.999) == 1002.0
        # assert ExchangeInterface._scale_price(ins_details, 2.555) == 2.6

    def test_check_quantity_within_limits(self):
        ins_details = {
            "min_order_size": 50,
            "min_order_size_scale": 2,
            "max_order_size": 500,
            "max_order_size_scale": 2,
        }
        assert not ExchangeInterface._check_quantity_within_limits(ins_details, 0.01)
        assert ExchangeInterface._check_quantity_within_limits(ins_details, 0.6)
        assert ExchangeInterface._check_quantity_within_limits(ins_details, 1)
        assert not ExchangeInterface._check_quantity_within_limits(ins_details, 5.1)

    def test_check_available_balance(self):

        exi = ExchangeInterface(instruments=[Instrument.BTCUSD])
        exi.ws = MockWebsocketClient
        exi.ws.balances = {"BTC": {"available": 1}, "USD": {"available": 1000}}
        ins_details = {
            "symbol": "BTC-USD",
            "base_currency": "BTC",
            "base_currency_scale": 8,
            "counter_currency": "USD",
        }
        assert exi._check_available_balance(ins_details, OrderSide.BUY, 0.5, 10000)
        assert not exi._check_available_balance(ins_details, OrderSide.BUY, 5, 10000)
        assert not exi._check_available_balance(ins_details, OrderSide.SELL, 0.5, 10000)
        assert exi._check_available_balance(ins_details, OrderSide.SELL, 0.09, 10000)
