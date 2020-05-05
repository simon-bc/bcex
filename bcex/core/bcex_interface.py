import atexit
import logging
import math
import signal

from bcex.core.orders import Order, OrderSide, OrderType, TimeInForce
from bcex.core.websocket_client import BcexClient, Book, Channel, Environment


class BcexInterface:
    """Interface for the Bcex Exchange

    Attributes
    ----------
    client: BcexClient
        websocket client to handle interactions with the exchange
    """

    REQUIRED_CHANNELS = [
        Channel.SYMBOLS,
        Channel.TICKER,
        Channel.TRADES,
    ]

    def __init__(
        self,
        symbols,
        api_secret=None,
        env=Environment.STAGING,
        channels=None,
        channel_kwargs=None,
        cancel_position_on_exit=True,
    ):
        """
        Parameters
        ----------
        symbols : list of str
            if multiple symbols then a list if a single symbol then a string or list.
            Symbols that you want the client to subscribe to
        channels : list of Channel,
            channels to subscribe to. if not provided all channels will be subscribed to.
            Some Public channels are symbols specific and will subscribe to provided symbols
        env : Environment
            environment to run in
            api key on exchange.blockchain.com gives access to Production environment
            To obtain access to staging environment, request to our support center needs to be made
        api_secret : str
            api key for the exchange which can be obtained once logged in, in settings (click on username) > Api
            if not provided, the api key will be taken from environment variable BCEX_API_SECRET
        """
        if channels is not None:
            # make sure we include the required channels
            channels = list(set(self.REQUIRED_CHANNELS + channels))

        self.client = BcexClient(
            symbols,
            channels=channels,
            channel_kwargs=channel_kwargs,
            api_secret=api_secret,
            env=env,
            cancel_position_on_exit=cancel_position_on_exit,
        )
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

    def connect(self):
        """Connects to the Blockchain.com Exchange Websocket"""
        # TODO: ensure that we are connected before moving forward
        self.client.connect()

    def exit(self):
        """Closes Websocket"""
        self.client.exit()

    def is_open(self):
        """Check that websockets are still open."""
        return self.client.ws is not None and not self.client.exited

    @staticmethod
    def _scale_quantity(symbol_details, quantity):
        """Scales the quantity for an order to the given scale

        Parameters
        ----------
        symbol_details : dict
            dictionary of details from the symbols from the symbols channel
        quantity : float
            quantity of order

        Returns
        -------
        quantity : float
            quantity of order scaled to required level
        """
        quantity = round(quantity, symbol_details["base_currency_scale"])
        return quantity

    @staticmethod
    def _scale_price(symbol_details, price):
        """Scales the price for an order to the given scale

        Parameters
        ----------
        symbol_details : dict
            dictionary of details from the symbols from the symbols channel
        price : float
            price of order

        Returns
        -------
        price : float
            price of order scaled to required level
        """
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
        """Checks if the quantity for the order is acceptable for the given symbol

        Parameters
        ----------
        symbol_details : dict
            dictionary of details from the symbols from the symbols channel
        quantity : float
            quantity of order

        Returns
        -------
        result : bool
        """
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
        """Checks if the quantity requested is possible with given balance

        Parameters
        ----------
        symbol_details : dict
            dictionary of details from the symbols from the symbols channel
        side : OrderSide enum
        quantity : float
            quantity of order
        price : float
            price of order

        Returns
        -------
        result : bool
        """
        if side == OrderSide.BUY:
            currency = symbol_details["base_currency"]
            quantity_in_currency = quantity
        else:
            currency = symbol_details["counter_currency"]
            quantity_in_currency = quantity * price
        balances = self.get_balances()
        available_balance = balances[currency]["available"]
        if available_balance > quantity_in_currency:
            return True

        logging.warning(
            f"Not enough available balance {available_balance} in {currency} for trade quantity {quantity}"
        )
        return False

    def tick_size(self, symbol):
        """Gets the tick size for given symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        tick_size : float
        """
        if not self._has_symbol_details(symbol):
            return None

        details = self.client.symbol_details[symbol]
        return (
            details["min_price_increment"] / 10 ** details["min_price_increment_scale"]
        )

    def lot_size(self, symbol):
        """Gets the lot size for given symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        lot_size : float
        """
        if not self._has_symbol_details(symbol):
            return None

        details = self.client.symbol_details[symbol]
        return details["min_order_size"] / 10 ** details["min_order_size_scale"]

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
        """Creates orders in correct format

        Parameters
        ----------
        symbol : Symbol
        side : OrderSide enum
        quantity : float
            quantity of order
        price : float
            price of order
        order_type : OrderType
        time_in_force : TimeInForce
            Time in force, applicable for orders except market orders
        minimum_quantity : float
            The minimum quantity required for an TimeInForce.IOC fill
        expiry_date : int YYYYMMDD
            Expiry date required for GTD orders
        stop_price : float
            Price to trigger the stop order
        check_balance : bool
            check if balance is sufficient for order

        Returns
        -------
        order : Order or None
            Order if we could create the order with the provided details
            None if we could not
        """
        if not self._has_symbol_details(symbol):
            return None

        symbol_details = self.client.symbol_details[symbol]
        quantity = self._scale_quantity(symbol_details, quantity)
        if not self._check_quantity_within_limits(symbol_details, quantity):
            return None
        if price is not None:
            price = self._scale_price(symbol_details, price)
        if check_balance and order_type == OrderType.LIMIT:
            has_balance = self._check_available_balance(
                symbol_details, side, quantity, price
            )
            if not has_balance:
                return None
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
        """Place order with valid quantity and prices

        It uses information from the symbols table to ensure our price and quantity conform to the exchange requirements
        If necessary, prices and quantities will be rounded to make it a valid order.


        Parameters
        ----------
        symbol : Symbol
        side : OrderSide enum
        quantity : float
            quantity of order
        price : float
            price of order
        order_type : OrderType
        time_in_force : TimeInForce
            Time in force, applicable for orders except market orders
        minimum_quantity : float
            The minimum quantity required for an TimeInForce.IOC fill
        expiry_date : int YYYYMMDD
            Expiry date required for GTD orders
        stop_price : float
            Price to trigger the stop order
        check_balance : bool
            check if balance is sufficient for order

        """
        if not self._has_symbol_details(symbol):
            return

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
        if order is not None:
            self.client.send_order(order)

    def _has_symbol_details(self, symbol):
        if (
            symbol in self.client.symbol_details
            and len(self.client.symbol_details[symbol]) > 0
        ):
            return True
        else:
            # log why
            if (
                symbol not in self.client.channel_status[Channel.SYMBOLS]
                or self.client.channel_status[Channel.SYMBOLS][symbol] != "subscribed"
            ):
                logging.warning(
                    f"Could not find symbol details for symbol {symbol}. Websocket it is not subscribed to it"
                )
            else:
                logging.error(
                    f"Could not find symbol details for {symbol} even if we subscribed to it. Might come later ?"
                )

    def cancel_all_orders(self):
        """Cancel all orders

        Notes
        -----
        This also cancels the orders for symbols which are not in self.symbols
        """
        self.client.cancel_all_orders()
        # TODO: wait for a response that all orders have been cancelled - MAX_TIMEOUT then warn/err

    def cancel_order(self, order_id):
        """Cancel specific order

        Parameters
        ----------
        order_id : str
            order id to cancel

        """
        self.client.send_order(
            Order(
                OrderType.CANCEL,
                order_id=order_id,
                symbol=self.get_order_details(order_id).symbol,
            )
        )

    def cancel_orders_for_symbol(self, symbol):
        """Cancel all orders for symbol

        Parameters
        ----------
        symbol : Symbol

        """
        order_ids = self.client.open_orders[symbol].keys()
        for o in order_ids:
            self.cancel_order(o)

    def get_last_traded_price(self, symbol):
        """Get the last matched price for the given symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        last_traded_price : float
            last matched price for symbol
        """
        return self.client.tickers.get(symbol, {}).get("last_trade_price")

    def get_ask_price(self, symbol):
        """Get the ask price for the given symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        ask_price : float
            ask price for symbol
        """
        # sorted dict - first key is lowest price
        book = self.client.l2_book[symbol][Book.ASK]
        return book.peekitem(0) if len(book) > 0 else None

    def get_bid_price(self, symbol):
        """Get the bid price for the given symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        bid_price : float
            bid price for symbol
        """
        # sorted dict - last key is highest price
        book = self.client.l2_book[symbol][Book.BID]
        return book.peekitem(-1) if len(book) > 0 else None

    def get_all_open_orders(self, symbols=None, to_dict=False):
        """Gets all the open orders

        Parameters
        ----------
        symbols : Symbol
        to_dict : bool
            convert the OrderResponses to a dict

        Returns
        -------
        open_orders : dict
            dict of all the open orders, key is the order id and values are order details
        """
        open_orders = {}
        if symbols is None:
            symbols = self.client.open_orders.keys()
        for i in symbols:
            open_orders.update(self.client.open_orders[i])
        if to_dict:
            return {k: o.to_dict() for k, o in open_orders.items()}
        else:
            return open_orders

    def get_order_details(self, order_id, symbol=None):
        """Get order details for a specific order

        Parameters
        ----------
        order_id : str
            order id for requested order
        symbol : Symbol
            if none have to search all symbols until it is found

        Returns
        -------
        order_details : OrderResponse
            details for specific order type depends on the to dict value
        """
        if symbol is not None:
            symbols = [symbol]
        else:
            symbols = self.client.open_orders.keys()

        for i in symbols:
            order_details = self.client.open_orders[i].get(order_id)
            if order_details is not None:
                return order_details

        return None

    def get_available_balance(self, coin):
        """
        Returns
        -------
        float: the available balance of the coin
        """
        return self.client.balances.get(coin, {}).get("available", 0)

    def get_order_book(self, symbol):
        """Get full order book for

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        order_book : Dict
        """
        return self.client.l2_book[symbol]

    def get_balances(self):
        """Get user balances"""
        return self.client.balances

    def get_symbols(self):
        """Get all the symbols"""
        return self.client.symbols

    def get_candles(self, symbol):
        """Get candles for symbol

        Parameters
        ----------
        symbol : Symbol

        Returns
        -------
        candles : list
            list of candles at timestamp
        """
        return self.client.candles[symbol]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    exchange = BcexInterface(["BTC-USD", "ETH-USD"])

    exchange.connect()
    while True:
        pass
