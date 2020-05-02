from unittest.mock import Mock, patch

from bcex.core.exchange_interface import ExchangeInterface
from bcex.core.orders import OrderSide
from bcex.core.symbol import Symbol
from bcex.core.websocket_client import Channel, Environment, MockBcexClient


class TestExchangeInterface:
    @patch("bcex.bcex.core.exchange_interface.BcexClient", return_value=Mock())
    def test_init(self, mock_client):
        exi = ExchangeInterface(
            [Symbol.ETHBTC, Symbol.BTCPAX],
            api_secret="14567",
            env=Environment.STAGING,
            channels=None,
            channels_kwargs={Channel.PRICES: {"granularity": 60}},
            cancel_position_on_exit=False,
        )
        assert exi.ws.call_count == 1
        assert exi.ws.call_args[0][0] == [Symbol.ETHBTC, Symbol.BTCPAX]

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

        exi = ExchangeInterface(symbols=[Symbol.BTCUSD])
        exi.ws = MockBcexClient(symbols=[Symbol.BTCUSD])
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

    def test_get_last_traded_price(self):
        exi = ExchangeInterface(symbols=[Symbol.ETHBTC])
        exi.ws = MockBcexClient(symbols=[Symbol.ETHBTC])

        exi.ws.tickers = {}
        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act is None

        exi.ws.tickers = {Symbol.ETHBTC: {"volume_24h": 13.1, "price_24h": 21.139}}
        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act is None

        exi.ws.tickers = {
            Symbol.ETHBTC: {
                "volume_24h": 13.1,
                "price_24h": 21.139,
                "last_trade_price": 20.120,
            }
        }
        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act == 20.120

    def test_connect(self):
        exi = ExchangeInterface(symbols=[Symbol.ETHBTC])
        exi.ws = MockBcexClient(symbols=[Symbol.ETHBTC])
        exi.ws.connect = Mock()

        exi.connect()
        assert exi.ws.connect.call_count == 1

    def test_exit(self):
        exi = ExchangeInterface(symbols=[Symbol.ETHBTC])
        exi.ws = MockBcexClient(symbols=[Symbol.ETHBTC])
        exi.ws.exit = Mock()

        exi.exit()
        assert exi.ws.exit.call_count == 1

    def test_is_open(self):
        exi = ExchangeInterface(symbols=[Symbol.ETHBTC])
        exi.ws = None

        assert not exi.is_open()

        exi.ws = MockBcexClient(symbols=[Symbol.ETHBTC])
        assert exi.is_open()

        exi.ws.exited = True
        assert not exi.is_open()
