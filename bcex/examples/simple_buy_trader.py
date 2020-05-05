import logging

from bcex.core.symbol import Symbol
from bcex.core.websocket_client import Environment, Channel
from bcex.examples.trader import BaseTrader


class SimpleBuyTrader(BaseTrader):
    CHANNELS = [
        Channel.HEARTBEAT,
        Channel.TRADING,
        Channel.BALANCES,
        Channel.SYMBOLS,
        Channel.AUTH,
    ]

    def __init__(
        self, symbol, quantity=0.05, env=Environment.PROD, buy_intervals=3600,
    ):
        super().__init__(
            symbol, refresh_rate=buy_intervals, env=env,
        )
        self.quantity = quantity

    def handle_orders(self):
        self.exchange.buy(self.symbol, self.quantity)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s", level=logging.DEBUG
    )
    trader = SimpleBuyTrader(Symbol.BTCUSD, buy_intervals=10, env=Environment.STAGING)
    trader.run_loop()
