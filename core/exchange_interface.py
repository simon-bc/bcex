import math
import logging

from core.orders import Order, OrderType, OrderSide, TimeInForce
from core.websocket_client import BcexClient, Environment, Channel, Book


class ExchangeInterface:
    REQUIRED_CHANNELS = [Channel.SYMBOLS, Channel.TICKER, Channel.TRADES]

    def __init__(
        self,
        instruments,
        api_key=None,
        env=Environment.STAGING,
        channels=REQUIRED_CHANNELS,
    ):
        self.ws = BcexClient(instruments, channels=channels, api_key=api_key, env=env)

    def connect(self):
        # TODO: ensure that we are connected before moving forward
        self.ws.connect()


    @staticmethod
    def _scale_quantity(instr_details, quantity):
        quantity = round(quantity, instr_details["base_currency_scale"])
        return quantity

    @staticmethod
    def _scale_price(instr_details, price):
        price_multiple = (
            price * 10 ** instr_details["min_price_increment_scale"]
        ) / instr_details["min_price_increment"]
        price = (
            math.floor(price_multiple)
            * instr_details["min_price_increment"]
            / 10 ** instr_details["min_price_increment_scale"]
        )
        return price

    @staticmethod
    def _check_quantity_within_limits(instr_details, quantity):
        max_limit = instr_details["max_order_size"] / (
            10 ** instr_details["max_order_size_scale"]
        )
        min_limit = instr_details["min_order_size"] / (
            10 ** instr_details["min_order_size_scale"]
        )
        if quantity < min_limit:
            logging.warning(f"Quantity {quantity} less than min {min_limit}")
            return False
        if max_limit == 0:
            return True
        if quantity > max_limit:
            logging.warning(f"Quantity {quantity} more than max {max_limit}")
            return False
        return True

    def _check_available_balance(self, instr_details, side, quantity, price):
        if side == OrderSide.BUY:
            currency = instr_details["base_currency"]
            quantity_in_currency = quantity
        else:
            currency = instr_details["counter_currency"]
            quantity_in_currency = quantity * price
        balances = self.get_balance()
        available_balance = balances[currency]["available"]
        if available_balance > quantity_in_currency:
            return True

        logging.warning(
            f"Not enough available balance {available_balance} in {currency} for trade quantity {quantity}"
        )
        return False

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
        check_balance=False,
    ):
        # assumes websocket has subscribed to symbol details of this instrument
        instr_details = self.ws.symbol_details[instrument]
        quantity = self._scale_quantity(instr_details, quantity)
        if not self._check_quantity_within_limits(instr_details, quantity):
            return False
        if price is not None:
            price = self._scale_price(instr_details, price)
        if check_balance and order_type == OrderType.LIMIT:
            has_balance = self._check_available_balance(
                instr_details, side, quantity, price
            )
            if not has_balance:
                return False
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
        check_balance=False,
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
            check_balance,
        )
        if order is not False:
            self.ws.send_order(order)

    def cancel_all_orders(self):
        self.ws.cancel_all_orders()
        # TODO: wait for a response that all orders have been cancelled - MAX_TIMEOUT then warn/err

    def cancel_order(self, order_id):
        self.ws.send_order(Order(OrderType.CANCEL, order_id=order_id))

    def cancel_orders_for_instrument(self, instrument):
        order_ids = self.ws.open_orders[instrument].keys()
        for o in order_ids:
            self.cancel_order(o)

    def get_last_traded_price(self, instrument):
        return self.ws.tickers.get(instrument)

    def get_ask_price(self, instrument):
        return self.ws.l2_book[instrument][Book.ASK].peekitem(0)

    def get_bid_price(self, instrument):
        return self.ws.l2_book[instrument][Book.ASK].peekitem(0)

    def get_all_open_orders(self, instruments=None):
        open_orders = {}
        if instruments is None:
            instruments = self.ws.open_orders.keys()
        for i in instruments:
            open_orders.update(self.ws.open_orders[i])
        return {k: o.to_dict() for k, o in open_orders.items()}

    def get_order_details(self, order_id, instrument=None):
        if instrument:
            order = self.ws.open_orders[instrument].get(order_id)
            if order is None:
                return order
            return order.to_dict()
        instruments = self.ws.open_orders.keys()
        for i in instruments:
            order_details = self.ws.open_orders[i].get(order_id)
            if order_details:
                return order_details.to_dict()
        return None

    def get_balance(self):
        return self.ws.balances

    def get_instruments(self):
        return self.ws.symbols


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
