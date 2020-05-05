import logging
import os
import sys
import time

from bcex.core.bcex_interface import BcexInterface
from bcex.core.orders import OrderSide, OrderType, TimeInForce
from bcex.core.websocket_client import Channel, Environment


class BaseTrader:
    CHANNELS = Channel.PRIVATE + [Channel.TICKER, Channel.SYMBOLS]

    def __init__(
        self,
        symbol,
        api_key=None,
        env=Environment.STAGING,
        refresh_rate=5,
        channels_kwargs=None,
    ):
        self.exchange = BcexInterface(
            [symbol],
            api_secret=api_key,
            env=env,
            channels=self.CHANNELS,
            channel_kwargs=channels_kwargs,
        )
        self.exchange.connect()
        self._symbol = symbol
        self._refresh_rate = refresh_rate

        # TODO: might want to extend the cancellation of open orders to symbol specific?
        self.reset()

    @property
    def refresh_rate(self):
        return self._refresh_rate

    @property
    def symbol(self):
        return self._symbol

    def reset(self):
        logging.info("Cancelling all existing orders before moving forward")
        self.exchange.cancel_all_orders()

    def handle_orders(self):
        raise NotImplementedError("This should be implemented in subclass")

    def restart(self):
        # This is what bitmex one does - seems like it executes to whole script again - pretty cool?
        logging.warning("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def run_loop(self):
        while True:
            if not self.exchange.is_open():
                logging.error("Websocket has disconnected. Attempting to restart")
                self.restart()

            self.handle_orders()

            time.sleep(self.refresh_rate)


class BasicLadderQuotes(BaseTrader):
    """Simple MM that places orders at regular intervals from last traded price

    Attributes
    -----------

    symbol: String,
        which symbol we are placing orders for

    n_levels : int,
        how many different price levels are we  quoting on each side of the book

    n_lots : int,
        represents order size i.e. qty = n_lots * order_size_tick

    """

    def __init__(self, symbol, n_levels, n_lots, **kwargs):
        super().__init__(symbol, **kwargs)
        self._n_levels = n_levels
        self._n_lots = n_lots
        self._tick_size = None
        self._lot_size = None

    @property
    def n_levels(self):
        return self._n_levels

    @property
    def n_lots(self):
        return self._n_lots

    def _check_orders(self, orders):
        # TODO: enforce balance checks
        return orders

    @property
    def tick_size(self):
        if self._tick_size is None:
            self._tick_size = self.exchange.tick_size(self.symbol)
        return self._tick_size

    @property
    def lot_size(self):
        if self._lot_size is None:
            self._lot_size = self.exchange.lot_size(self.symbol)
        return self._lot_size

    def handle_orders(self):
        # Cancel all existing orders
        # TODO: add order deltas
        self.exchange.cancel_all_orders()

        # This forms our base price - we add a ladder of orders around it
        lpm = self.exchange.get_last_traded_price(self.symbol)
        for k in range(1, self.n_levels + 1):
            self.exchange.place_order(
                symbol=self.symbol,
                side=OrderSide.BUY,
                quantity=self.n_lots * self.lot_size,
                price=lpm - k * self.tick_size,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
            )

            self.exchange.place_order(
                symbol=self.symbol,
                side=OrderSide.SELL,
                quantity=self.n_lots * self.lot_size,
                price=lpm + k * self.tick_size,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
            )

        # # TODO: might be nice if we could send a list of orders to the exchange interface
        # buy_orders = [
        #     Order(
        #         OrderType.LIMIT,
        #         instrument=self.symbol,
        #         price=lpm - n * self.exchange.tick_size(self.symbol),
        #         side=OrderSide.BUY,
        #         time_in_force=TimeInForce.GTC,
        #         order_quantity=self.n_lots * self.exchange.lot_size(self.symbol)
        #     )
        #     for n in range(1, self.n_levels + 1)
        # ]
        #
        # sell_orders = [
        #     Order(
        #         OrderType.LIMIT,
        #         instrument=self.symbol,
        #         price=lpm + n * self.exchange.tick_size(self.symbol),
        #         side=OrderSide.SELL,
        #         time_in_force=TimeInForce.GTC,
        #         order_quantity=self.n_lots * self.exchange.lot_size(self.symbol)
        #     )
        #     for n in range(1, self.n_levels + 1)
        #
        # ]
        #
        # orders = self._check_orders(buy_orders + sell_orders)
        # [
        #     self.exchange.ws.send_order(order) for order in orders
        # ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    trader = BasicLadderQuotes("ETH-BTC", 5, 3, refresh_rate=5)

    trader.run_loop()
