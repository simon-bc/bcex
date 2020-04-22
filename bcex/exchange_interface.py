import math

from copy import deepcopy

from core.order_response import OrderStatus
from core.orders import Order, OrderType, OrderSide
from core.websocket_client import MessageChannel, AuthenticatedWebSocket, Environment


class PitInterface:
    REQUIRED_CHANNELS = [MessageChannel.SYMBOLS, MessageChannel.TICKER, MessageChannel.TRADES]

    def __init__(self, instruments, api_key=None, env=Environment.STAGING):
        self.ws = AuthenticatedWebSocket(instruments, channels=self.REQUIRED_CHANNELS,
                                         api_key=api_key,
                                         env=env)

    def connect(self):
        self.ws.connect()

    def _create_order(self, instrument, side, price, quantity):
        # assumes websocket has subscribed to symbol details of this instrument
        instr_details = self.ws.symbols[instrument]
        quantity = round(quantity, instr_details["base_currency_scale"])

        price_multiple = (price * 10 ** ins_details["min_price_increment_scale"]) \
                         / ins_details["min_price_increment"]
        if side == OrderSide.BUY:
            price = math.floor(price_multiple) * ins_details["min_price_increment"] / 10 ** \
                    ins_details["min_price_increment_scale"]
        else:
            price = math.ceil(price_multiple) * ins_details["min_price_increment"] / 10 ** \
                    ins_details["min_price_increment_scale"]

        return Order(OrderType.LIMIT, instrument=instrument, side=side, price=price, quantity=quantity)

    def place_order(self, instrument, side, price, quantity):
        """
        Use the information from the symbols table to ensure our price and quantity conform to the
        exchange requirements

        Parameters
        ----------
        instrument : str
        side : OrderSide enum
        price : float
        quantity : float

        """
        order = self._create_order(instrument, side, price, quantity)
        self.pit.send_order(order)

    def cancel_all_orders(self, instrument=None):
        for merid, status in deepcopy(self.pit.open_orders).items():
            if instrument is None or status not in OrderStatus.terminal_states():
                self.send_order(Order(OrderType.CANCEL, mercury_order_id=merid))

        # TODO: wait for a response that all orders have been cancelled - MAX_TIMEOUT then warn/err

    def get_last_traded_price(self, instrument):
        return self.pit.tickers.get(instrument)


if __name__ == "__main__":
    price = 9090.20

    ins_details = {'symbol': 'BTC-USD',
                   'base_currency': 'BTC',
                   'base_currency_scale': 8,
                   'counter_currency': 'USD',
                   'counter_currency_scale': 2,
                   'min_price_increment': 10,
                   'min_price_increment_scale': 2,
                   'min_order_size': 60000,
                   'min_order_size_scale': 8}

    price_multiple = (price * 10 ** ins_details["min_price_increment_scale"]) \
                     / ins_details["min_price_increment"]
    print(math.floor(price_multiple) * ins_details["min_price_increment"] / 10 ** ins_details[
        "min_price_increment_scale"])
