from unittest.mock import Mock, patch

from bcex.core.bcex_interface import BcexInterface
from bcex.core.orders import OrderSide, OrderType
from bcex.core.symbol import Symbol
from bcex.core.websocket_client import Channel, Environment, MockBcexClient


class TestBcexInterface:
    @patch("bcex.core.bcex_interface.BcexClient")
    def test_init(self, mock_client):
        mock_client.side_effect = MockBcexClient
        exi = BcexInterface(
            [Symbol.ETHBTC, Symbol.BTCPAX],
            api_secret="14567",
            env=Environment.STAGING,
            channels=None,
            channel_kwargs={Channel.PRICES: {"granularity": 60}},
            cancel_position_on_exit=False,
        )

        assert mock_client.call_count == 1
        assert mock_client.call_args[0][0] == [Symbol.ETHBTC, Symbol.BTCPAX]
        assert mock_client.call_args[1]["api_secret"] == "14567"
        assert mock_client.call_args[1]["env"] == Environment.STAGING
        assert mock_client.call_args[1]["channels"] is None
        assert mock_client.call_args[1]["channel_kwargs"] == {
            Channel.PRICES: {"granularity": 60}
        }
        assert mock_client.call_args[1]["cancel_position_on_exit"] is False

        mock_client.reset_mock()
        exi = BcexInterface(
            [Symbol.ETHBTC, Symbol.BTCPAX],
            api_secret=None,
            env=Environment.PROD,
            channels=[Channel.HEARTBEAT],
            channel_kwargs={Channel.PRICES: {"granularity": 60}},
            cancel_position_on_exit=True,
        )
        assert mock_client.call_count == 1
        assert mock_client.call_args[1]["api_secret"] is None
        assert mock_client.call_args[1]["env"] == Environment.PROD
        assert set(mock_client.call_args[1]["channels"]) == set(
            BcexInterface.REQUIRED_CHANNELS + [Channel.HEARTBEAT]
        )
        assert mock_client.call_args[1]["cancel_position_on_exit"] is True

    def test_required_channels(self):
        assert set(BcexInterface.REQUIRED_CHANNELS) == {
            Channel.SYMBOLS,
            Channel.TICKER,
            Channel.TRADES,
        }

    def test_scale_quantity(self):
        ins_details = {
            "base_currency_scale": 2,
        }
        assert BcexInterface._scale_quantity(ins_details, 0.01) == 0.01
        assert BcexInterface._scale_quantity(ins_details, 0.011) == 0.01
        # assert BcexInterface._scale_quantity(ins_details, 0.0199) == 0.02
        # assert BcexInterface._scale_quantity(ins_details, 2.555) == 2.56
        # assert BcexInterface._scale_quantity(ins_details, 1222) == 1222

    def test_scale_price(self):
        ins_details = {"min_price_increment": 10, "min_price_increment_scale": 2}
        assert BcexInterface._scale_price(ins_details, 1000) == 1000
        assert BcexInterface._scale_price(ins_details, 1000.001) == 1000
        assert BcexInterface._scale_price(ins_details, 1000.01) == 1000
        assert BcexInterface._scale_price(ins_details, 1000.1) == 1000.1
        # assert BcexInterface._scale_price(ins_details, 1001.999) == 1002.0
        # assert BcexInterface._scale_price(ins_details, 2.555) == 2.6

    def test_check_quantity_within_limits(self):
        ins_details = {
            "min_order_size": 50,
            "min_order_size_scale": 2,
            "max_order_size": 500,
            "max_order_size_scale": 2,
        }
        assert not BcexInterface._check_quantity_within_limits(ins_details, 0.01)
        assert BcexInterface._check_quantity_within_limits(ins_details, 0.6)
        assert BcexInterface._check_quantity_within_limits(ins_details, 1)
        assert not BcexInterface._check_quantity_within_limits(ins_details, 5.1)

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_check_available_balance(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.BTCUSD])
        assert mock_client.call_count == 1

        exi.client.balances.update(
            {"BTC": {"available": 1}, "USD": {"available": 1000}}
        )

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

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_get_last_traded_price(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1

        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act is None

        exi.client.tickers.update(
            {Symbol.ETHBTC: {"volume_24h": 13.1, "price_24h": 21.139}}
        )

        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act is None

        exi.client.tickers = {
            Symbol.ETHBTC: {
                "volume_24h": 13.1,
                "price_24h": 21.139,
                "last_trade_price": 20.120,
            }
        }
        act = exi.get_last_traded_price(Symbol.ETHBTC)
        assert act == 20.120

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_connect(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1
        exi.client.connect = Mock()

        exi.connect()
        assert exi.client.connect.call_count == 1

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_exit(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.BTCUSD])
        assert mock_client.call_count == 1
        exi.client.exit = Mock()

        exi.exit()
        assert exi.client.exit.call_count == 1

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_is_open(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1

        assert not exi.is_open()

        exi.client.ws = Mock()
        assert exi.is_open()

        exi.client.exited = True
        assert not exi.is_open()

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_place_order(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1

        exi.client.send_order = Mock()

        # no symbol details available
        exi.place_order(Symbol.BTCPAX, 100, 10.3)
        assert exi.client.send_order.call_count == 0

        # symbol available
        exi.client.symbol_details[Symbol.BTCPAX] = {
            "min_price_increment": 10,
            "min_price_increment_scale": 2,
            "base_currency_scale": 2,
            "min_order_size": 50,
            "min_order_size_scale": 2,
            "max_order_size": 500,
            "max_order_size_scale": 2,
        }

        exi.place_order(
            Symbol.BTCPAX,
            OrderSide.SELL,
            quantity=1.01,
            price=1000.001,
            order_type=OrderType.LIMIT,
            post_only=True,
        )
        assert exi.client.send_order.call_count == 1
        act_order = exi.client.send_order.call_args[0][0]

        assert act_order is not None
        assert act_order.order_quantity == 1.01
        assert act_order.price == 1000
        assert act_order.post_only is True
        # symbol available but wrong parameters : too big quantity
        exi.client.send_order.reset_mock()
        exi.place_order(
            Symbol.BTCPAX,
            OrderSide.SELL,
            quantity=1000000000000000.113,
            price=1000.001,
            order_type=OrderType.LIMIT,
        )
        assert exi.client.send_order.call_count == 0

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_create_order(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_tick_size(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.BTCPAX])
        assert mock_client.call_count == 1

        # no information about symbol
        assert exi.tick_size(Symbol.BTCPAX) is None

        exi.client.symbol_details[Symbol.BTCPAX] = {
            "min_price_increment": 6,
            "min_price_increment_scale": 3,
        }

        act_tick_size = exi.tick_size(Symbol.BTCPAX)
        assert act_tick_size == 0.006

    @patch("bcex.core.bcex_interface.BcexClient", side_effect=MockBcexClient)
    def test_lot_size(self, mock_client):
        exi = BcexInterface(symbols=[Symbol.ETHBTC])
        assert mock_client.call_count == 1

        # no information about symbol
        assert exi.lot_size(Symbol.ETHBTC) is None

        exi.client.symbol_details[Symbol.ETHBTC] = {
            "min_order_size": 50,
            "min_order_size_scale": 2,
        }
        act_lot_size = exi.lot_size(Symbol.ETHBTC)
        assert act_lot_size == 0.5

        # another symbol
        assert exi.lot_size(Symbol.ALGOBTC) is None
