import math
from copy import deepcopy

from core.order_response import OrderStatus
from core.orders import Order, OrderType, OrderSide, TimeInForce
from core.websocket_client import BcexClient, Environment, Channel


class ExchangeInterface:
    REQUIRED_CHANNELS = [Channel.SYMBOLS, Channel.TICKER, Channel.TRADES]

    def __init__(self, instruments, api_key=None, env=Environment.STAGING):
        self.ws = BcexClient(
            instruments, channels=self.REQUIRED_CHANNELS, api_key=api_key, env=env
        )

    def connect(self):
        self.ws.connect()

    def _scale_quantity(self, instrument, quantity):
        instr_details = self.ws.symbol_details[instrument]
        quantity = round(quantity, instr_details["base_currency_scale"])
        return quantity

    def _scale_price(self, instrument, price):
        instr_details = self.ws.symbol_details[instrument]
        price_multiple = (
            price * 10 ** instr_details["min_price_increment_scale"]
        ) / instr_details["min_price_increment"]
        price = (
            math.floor(price_multiple)
            * ins_details["min_price_increment"]
            / 10 ** instr_details["min_price_increment_scale"]
        )
        return price

    def _create_order(
        self,
        instrument,
        side,
        quantity,
        price,
        order_type,
        time_in_force,
        minimum_quantity,
        expiry_date,
        stop_price,
    ):
        # assumes websocket has subscribed to symbol details of this instrument
        quantity = self._scale_quantity(instrument, quantity)
        if price is not None:
            price = self._scale_price(instrument, price)

        return Order(
            order_type=order_type,
            instrument=instrument,
            side=side,
            price=price,
            order_quantity=quantity,
            time_in_force=time_in_force,
            minimum_quantity=minimum_quantity,
            expiry_date=expiry_date,
            stop_price=stop_price,
        )

    def place_order(
        self,
        instrument,
        side,
        quantity,
        price=None,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        minimum_quantity=None,
        expiry_date=None,
        stop_price=None,
    ):
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
        order = self._create_order(
            instrument,
            side,
            quantity,
            price,
            order_type,
            time_in_force,
            minimum_quantity,
            expiry_date,
            stop_price,
        )
        self.ws.send_order(order)

    def cancel_all_orders(self, instrument=None):
        for merid, status in deepcopy(self.ws.open_orders).items():
            if instrument is None or status not in OrderStatus.terminal_states():
                self.ws.send_order(Order(OrderType.CANCEL, order_id=merid))

        # TODO: wait for a response that all orders have been cancelled - MAX_TIMEOUT then warn/err

    def get_last_traded_price(self, instrument):
        return self.ws.tickers.get(instrument)


if __name__ == "__main__":
    price = 9090.20

    ins_details = {
        "symbol": "BTC-USD",
        "base_currency": "BTC",
        "base_currency_scale": 8,
        "counter_currency": "USD",
        "counter_currency_scale": 2,
        "min_price_increment": 10,
        "min_price_increment_scale": 2,
        "min_order_size": 60000,
        "min_order_size_scale": 8,
    }

    price_multiple = (
        price * 10 ** ins_details["min_price_increment_scale"]
    ) / ins_details["min_price_increment"]
    print(
        math.floor(price_multiple)
        * ins_details["min_price_increment"]
        / 10 ** ins_details["min_price_increment_scale"]
    )
