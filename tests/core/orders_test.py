import pytest
from bcex.core.orders import Order, OrderSide, OrderType, TimeInForce


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
                side=None,
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
