import pytest

from bcex.core.orders import Order, OrderSide, OrderType, TimeInForce, OrderAction
from bcex.core.symbol import Symbol
from bcex.core.websocket_client import Channel


class TestOrder(object):
    def test_create_order(self):
        Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        Order(
            symbol="BTC-USD",
            order_type=OrderType.MARKET,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        Order(
            symbol="BTC-USD",
            order_type=OrderType.STOP,
            stop_price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        )
        Order(symbol="BTC-USD", order_type=OrderType.CANCEL, order_id="test")
        Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.IOC,
            minimum_quantity=1,
        )
        Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            expiry_date="20201010",
        )

        Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            post_only=True,
        )

        with pytest.raises(ValueError):
            Order(
                order_type=OrderType.LIMIT,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.MARKET,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.MARKET,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=None,
            )

        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.MARKET,
                price=100,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )

        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.LIMIT,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTD,
            )
        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.STOP,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.STOP_LIMIT,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )
        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.LIMIT,
                price=1,
                order_quantity=1,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.IOC,
            )

        with pytest.raises(ValueError):
            Order(
                symbol="BTC-USD",
                order_type=OrderType.MARKET,
                order_quantity=1,
                side=OrderSide.SELL,
                post_only=True,
                time_in_force=TimeInForce.GTC,
            )

    def test_order_to_dict(self):
        o1 = Order(
            symbol="BTC-USD", order_type=OrderType.CANCEL, order_id="test1"
        ).order_to_dict()
        assert o1.keys() == {"orderID", "channel", "action"}
        assert o1["orderID"] == "test1"
        assert o1["channel"] == Channel.TRADING
        assert o1["action"] == OrderAction.CANCEL_ORDER

        o2 = Order(
            symbol="BTC-USD", order_type=OrderType.CANCEL, order_id=-999
        ).order_to_dict()
        # if -999 will trigger bulk cancel
        assert o2.keys() == {"orderID", "channel", "action"}
        assert o2["orderID"] == -999
        assert o2["channel"] == Channel.TRADING
        assert o2["action"] == OrderAction.BULK_CANCEL

        o3 = Order(
            symbol=Symbol.BTCUSD,
            order_type=OrderType.LIMIT,
            price=1.213,
            order_quantity=103.1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.IOC,
            minimum_quantity=1,
            post_only=True,
        ).order_to_dict()

        assert o3["action"] == OrderAction.PLACE_ORDER
        assert o3["channel"] == Channel.TRADING
        assert o3["clOrdID"].endswith("_bcexpy")
        assert o3["ordType"] == OrderType.LIMIT
        assert o3["symbol"] == Symbol.BTCUSD
        assert o3["side"] == OrderSide.SELL
        assert o3["orderQty"] == 103.1
        assert o3["price"] == 1.213
        assert o3["execInst"] == "ALO"

        o4 = Order(
            symbol="BTC-USD",
            order_type=OrderType.STOP,
            stop_price=1.13,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
        ).order_to_dict()
        assert o4["stopPx"] == 1.13

        o5 = Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.IOC,
            minimum_quantity=0.01,
        ).order_to_dict()
        assert o5["minQty"] == 0.01

        o6 = Order(
            symbol="BTC-USD",
            order_type=OrderType.LIMIT,
            price=1,
            order_quantity=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTD,
            minimum_quantity=0.01,
            expiry_date="20200609",
        ).order_to_dict()
        assert o6["expireDate"] == "20200609"
