import logging
import math

from core.orders import Order, OrderSide, OrderType, TimeInForce
from core.websocket_client import BcexClient, Book, Channel, Environment


class ExchangeInterface:
    REQUIRED_CHANNELS = [Channel.SYMBOLS, Channel.TICKER, Channel.TRADES]

    def __init__(
        self,
        symbols,
        api_secret=None,
        env=Environment.STAGING,
        channels=REQUIRED_CHANNELS,
    ):
        self.ws = BcexClient(symbols, channels=channels, api_secret=api_secret, env=env)

    def connect(self):
        self.ws.connect()

    @staticmethod
    def _scale_quantity(symbol_details, quantity):
        quantity = round(quantity, symbol_details["base_currency_scale"])
        return quantity

    @staticmethod
    def _scale_price(symbol_details, price):
        price_multiple = (
            price * 10 ** symbol_details["min_price_increment_scale"]
        ) / symbol_details["min_price_increment"]
        price = (
            math.floor(price_multiple)
            * symbol_details["min_price_increment"]
            / 10 ** symbol_details["min_price_increment_scale"]
        )
        return price

    @staticmethod
    def _check_quantity_within_limits(symbol_details, quantity):
        max_limit = symbol_details["max_order_size"] / (
            10 ** symbol_details["max_order_size_scale"]
        )
        min_limit = symbol_details["min_order_size"] / (
            10 ** symbol_details["min_order_size_scale"]
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

    def _check_available_balance(self, symbol_details, side, quantity, price):
        if side == OrderSide.BUY:
            currency = symbol_details["base_currency"]
            quantity_in_currency = quantity
        else:
            currency = symbol_details["counter_currency"]
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
        symbol,
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
        # assumes websocket has subscribed to symbol details of this symbol
        symbol_details = self.ws.symbol_details[symbol]
        quantity = self._scale_quantity(symbol_details, quantity)
        if not self._check_quantity_within_limits(symbol_details, quantity):
            return False
        if price is not None:
            price = self._scale_price(symbol_details, price)
        if check_balance and order_type == OrderType.LIMIT:
            has_balance = self._check_available_balance(
                symbol_details, side, quantity, price
            )
            if not has_balance:
                return False
        return Order(
            order_type=order_type,
            symbol=symbol,
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
        symbol,
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
        symbol : str
        side : OrderSide enum
        price : float
        quantity : float

        """
        order = self._create_order(
            symbol,
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

    def cancel_orders_for_symbol(self, symbol):
        order_ids = self.ws.open_orders[symbol].keys()
        for o in order_ids:
            self.cancel_order(o)

    def get_last_traded_price(self, symbol):
        return self.ws.tickers.get(symbol)

    def get_ask_price(self, instrument):
        # sorted dict - first key is lowest price
        book = self.ws.l2_book[instrument][Book.ASK]
        return book.peekitem(0) if len(book) > 0 else None

    def get_bid_price(self, instrument):
        # sorted dict - last key is highest price
        book = self.ws.l2_book[instrument][Book.BID]
        return book.peekitem(-1) if len(book) > 0 else None

    def get_all_open_orders(self, symbols=None, to_dict=False):
        open_orders = {}
        if symbols is None:
            symbols = self.ws.open_orders.keys()
        for i in symbols:
            open_orders.update(self.ws.open_orders[i])
        if to_dict:
            return {k: o.to_dict() for k, o in open_orders.items()}
        else:
            return open_orders

    def get_order_details(self, order_id, symbol=None, to_dict=True):
        if symbol:
            order = self.ws.open_orders[symbol].get(order_id)
            if order is None:
                return order
            if to_dict:
                return order.to_dict()
            else:
                return order
        symbols = self.ws.open_orders.keys()
        for i in symbols:
            order_details = self.ws.open_orders[i].get(order_id)
            if order_details:
                if to_dict:
                    return order_details.to_dict()
                else:
                    return order_details
        return None

    def get_balance(self):
        return self.ws.balances

    def get_symbols(self):
        return self.ws.symbols

