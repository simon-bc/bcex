import pytest
from bcex.core.orders import OrderSide
from bcex.core.symbol import Symbol
from bcex.core.trade import Trade


class TestTrade:
    def test_init(self):
        trade = Trade(
            Symbol.ETHBTC,
            0.13,
            4.1,
            OrderSide.BUY,
            "2019-01-02T01:12",
            trade_id="13456323",
        )
        assert trade.symbol == Symbol.ETHBTC
        assert trade.price == 0.13
        assert trade.quantity == 4.1
        assert trade.side == OrderSide.BUY
        assert trade.timestamp == "2019-01-02T01:12"
        assert trade.trade_id == "13456323"

        # wrong trade side
        with pytest.raises(ValueError):
            trade = Trade(
                Symbol.ETHBTC, 0.13, 4.1, "13", "2019-01-02T01:12", trade_id="13456323"
            )
