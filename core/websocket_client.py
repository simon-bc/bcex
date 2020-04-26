import json
import logging
import os
import threading
import time
from collections import defaultdict

import websocket as webs
from core.order_response import OrderResponse, OrderStatus
from core.orders import Order, OrderType
from core.trade import Trade
from core.utils import parse_balance
from sortedcontainers import SortedDict as sd

MESSAGE_LIMIT = 1200  # number of messages per minute allowed


class Book:
    BID = "bids"
    ASK = "asks"


class Environment:
    STAGING = "Staging"
    PROD = "Production"


class Action:
    """An action describes what action to take for the provided channel
    """

    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class Channel:
    """A channel provides context about the type of data being communicated between the client and server.
    """

    HEARTBEAT = "heartbeat"  # Receive heartbeat messages
    L2 = "l2"  # Receive level 2 order book data (aggregated)
    L3 = "l3"  # Receive level 3 order book data (aggregated)
    PRICES = "prices"  # Receive candlestick market data
    SYMBOLS = "symbols"  # Receive symbol messages
    TICKER = "ticker"  # Receive ticker messages
    TRADES = "trades"  # Receive trade execution messages
    AUTH = "auth"  # To authenticate a web socket connection
    BALANCES = "balances"  # To receive balance updates
    TRADING = "trading"  # Submit & cancel orders, receive order snapshots and updates

    ALL = [HEARTBEAT, L2, L3, PRICES, SYMBOLS, TICKER, TRADES, AUTH, BALANCES, TRADING]
    PUBLIC = [HEARTBEAT, TICKER, PRICES, TRADES, L2, L3, SYMBOLS]
    PRIVATE = [AUTH, BALANCES, TRADING]


class Event:
    """Indicate the purpose of the message
    """

    UPDATED = "updated"  # An update corresponding to the channel has occurred
    SNAPSHOT = "snapshot"  # A channel snapshot has been provided
    REJECTED = "rejected"  # the last action for the channel was rejected
    SUBSCRIBED = "subscribed"  # The channel was successfully subscribed to
    UNSUBSCRIBED = "unsubscribed"  # The channel was successfully unsubscribed to

    ALL = [UPDATED, SNAPSHOT, REJECTED, SUBSCRIBED, UNSUBSCRIBED]


def _update_max_list(l, e, n):
    """Update a list and enforce maximum length"""
    l.append(e)
    return l[-n:]


class BcexClient(object):
    """Blockchain Exchange Websocket API client v1

    Attributes
    ----------
    balances : dict
    open_orders : dict

    Notes
    -----
    Official documentation for the api can be found in https://exchange.blockchain.com/api/
    """

    MAX_CANDLES_LEN = 200
    MAX_TRADES_LEN = 200

    def __init__(
        self,
        symbols,
        channels=None,
        channel_kwargs=None,
        env=Environment.STAGING,
        api_secret=None,
        cancel_position_on_exit=True,
    ):
        """This class connects to the PIT websocket client

        Parameters
        ----------
        symbols : list of str
            if multiple symbols then a list if a single symbol then a string or list.
            Symbols that you want the client to subscribe to
        channels : list of Channel,
            channels to subscribe to. if not provided all channels apart from L3 will be subscribed to.
            Private channels will be subscribed to only if an API key is provided
            Some Public channels are symbols specific and will subscribe to provided symbols
        channel_kwargs: dict
            kwargs that we may need to specify for the particular channel -e.g.  price granularity
        env : Environment
            environment to run in
            api key on exchange.blockchain.com gives access to Production environment
            To obtain access to staging environment, request to our support center needs to be made
        api_secret : str
            api key for the exchange which can be obtained once logged in, in settings (click on username) > Api
            if not provided, the api key will be taken from environment variable BCEX_API_SECRET
        cancel_position_on_exit: bool
            sends cancel all trades order on exit
        """
        if env == Environment.STAGING:
            ws_url = "wss://ws.staging.blockchain.info/mercury-gateway/v1/ws"
            origin_url = "https://pit.staging.blockchain.info"
        elif env == Environment.PROD:
            ws_url = "wss://ws.prod.blockchain.info/mercury-gateway/v1/ws"
            origin_url = "https://exchange.blockchain.com"
        else:
            raise ValueError(
                f"Environment {env} does not have associated ws, api and origin urls"
            )

        self.cancel_position_on_exit = cancel_position_on_exit
        self._error = None
        self.authenticated = False
        self.ws_url = ws_url
        self.origin = origin_url
        self.exited = False

        self.symbols = symbols
        self.symbol_details = {s: {} for s in symbols}
        self.channels = channels or list(
            set(Channel.ALL) - {Channel.L3}
        )  # L3 not handled yet
        self.channel_kwargs = channel_kwargs or {}

        # webs.enableTrace(True)
        self.ws = None
        self.wst = None

        self._api_secret = api_secret

        if api_secret is None and "BCEX_API_SECRET" in os.environ:
            self._api_secret = os.environ["BCEX_API_SECRET"]

        # use these dictionaries to store the data we receive
        self.balances = {}
        self.tickers = {}

        self.l2_book = {}
        for symbol in self.symbols:
            self.l2_book[symbol] = {"bids": sd(), "asks": sd()}

        self.candles = defaultdict(list)
        self.market_trades = defaultdict(list)
        self.open_orders = defaultdict(dict)

    def _check_attributes(self):
        for attr, _type in [
            ("symbols", list),
            ("channels", list),
            ("channel_kwargs", dict),
            ("url", str),
            ("api_url", str),
        ]:
            if not isinstance(getattr(self, attr), _type):
                raise ValueError(
                    f"{attr} should be a {_type} not {type(getattr(self, attr))}"
                )

    def _subscribe_channels(self):
        # Public channel subscriptions - symbol specific
        self._public_subscription()

        # Authenticated private subscriptions
        if self.api_secret is not None:
            self._private_subscription()
        else:
            logging.warning(
                f"Private channels will not be available because no API key was provided"
            )

    def _public_subscription(self):
        for channel in set(self.channels).intersection(set(Channel.PUBLIC)):
            for i in self.symbols:
                s = {"action": "subscribe", "channel": channel, "symbol": i}
                kwargs = self.channel_kwargs.get(channel)
                if kwargs:
                    s.update(kwargs)
                self.ws.send(json.dumps(s))

        # TODO: wait for public subscriptions to be complete i.e. wait for data from each
        # chosen channel to have retrieved some data

    def _private_subscription(self):
        self._authenticate()
        for channel in set(self.channels).intersection(set(Channel.PRIVATE)):
            if channel == Channel.AUTH:
                # already subscribed
                continue
            self.ws.send(json.dumps({"action": Action.SUBSCRIBE, "channel": channel}))

    def connect(self):
        """Connects to the websocket and runs it
        """
        self.ws = webs.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
            on_ping=None,
        )
        self.wst = threading.Thread(
            target=lambda: self.ws.run_forever(origin=self.origin)
        )
        self.wst.daemon = True
        self.wst.start()

        # Wait for connection before continuing
        conn_timeout = 5
        while (
            (not self.ws.sock or not self.ws.sock.connected)
            and conn_timeout
            and not self._error
        ):
            time.sleep(1)
            conn_timeout -= 1

        if not conn_timeout:  # i.e. if conn_timeout = 0
            logging.error("Couldn't connect to websocket! Exiting.")
            raise webs.WebSocketTimeoutException(
                "Couldn't connect to websocket! Exiting."
            )

        self._subscribe_channels()

    def on_open(self):
        """What to do when a new websocket opens
        """
        logging.info("-------- Websocket opened ---------")

    def on_close(self):
        """What to do when the websocket closes
        """
        self.exit()
        logging.warning("\n-- Websocket Closed --")

    def on_error(self, error):
        self._on_error(error)

    def _on_error(self, err):
        self._error = err
        logging.error(err)
        self.exit()

    def exit(self):
        if self.cancel_position_on_exit and self.authenticated:
            self.cancel_all_orders()
        self.ws.close()
        self.exited = True

    def on_message(self, msg):
        """Parses the message returned from the websocket depending on which channel returns it

        Parameters
        ----------
        msg : str
            incoming message from websocket
        """
        if msg is None:
            return

        msg = json.loads(msg)
        logging.debug(msg)
        # TODO: replace with generic`
        # getattr(self, f"_on_{msg['channel']}")(msg)

        if msg["channel"] == Channel.TRADING:
            self._on_trading_updates(msg)
        elif msg["channel"] == Channel.AUTH:
            self._on_auth_updates(msg)
        elif msg["channel"] == Channel.BALANCES:
            self._on_balance_updates(msg)
        elif msg["channel"] == Channel.TICKER:
            self._on_ticker_updates(msg)
        elif msg["channel"] == Channel.L2:
            self._on_l2_updates(msg)
        elif msg["channel"] == Channel.L3:
            self._on_l3_updates(msg)
        elif msg["channel"] == Channel.PRICES:
            self._on_price_updates(msg)
        elif msg["channel"] == Channel.HEARTBEAT:
            self._on_heartbeat_updates(msg)
        elif msg["channel"] == Channel.TRADES:
            self._on_market_trade(msg)
        elif msg["channel"] == Channel.SYMBOLS:
            self._on_symbols_updates(msg)
        else:
            self._on_message_unsupported(msg)

    def _on_message_unsupported(self, message):
        if message["channel"] in Channel.ALL:
            logging.warning(
                f"Messages from channel {message['channel']} not supported by client"
            )
        else:
            logging.error(
                f"Websocket returned a message with an unknown channel {message['channel']}"
            )

    def _on_symbols_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Successfully subscribed to symbols")
        elif msg["event"] == Event.SNAPSHOT:
            # TODO: double check
            symbol = msg["symbol"]
            self.symbol_details.update({symbol: msg})
        elif msg["event"] == Event.UPDATED:
            # TODO: should we drop the extra info
            symbol = msg["symbol"]
            self.symbol_details[symbol].update(msg)

    def _on_market_trade(self, msg):
        """Handle market trades by appending to symbol trade history"""
        symbol = msg["symbol"]
        if msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Successfully subscribed to trades for {symbol}")
        else:
            trades = self.market_trades[symbol]
            trade = Trade.parse_from_msg(msg)
            self.market_trades[symbol] = _update_max_list(
                trades, trade, self.MAX_TRADES_LEN
            )

    def _on_price_updates(self, msg):
        """ Store latest candle update and truncate list to length MAX_CANDLES_LEN"""
        if msg["event"] == Event.SUBSCRIBED:
            key = msg["symbol"]
            logging.info(f"{key} candles subscribed to.")
            logging.info(f"{msg['symbol']} candles subscribed to.")
        elif msg["event"] == Event.UPDATED:
            key = msg["symbol"]
            # TODO: what else would be inside the msg?
            if "price" in msg:
                candles = self.candles[key]
                self.candles[key] = _update_max_list(
                    candles, msg["price"], self.MAX_CANDLES_LEN
                )
        elif msg["event"] == Event.REJECTED:
            logging.warning(f"Price update rejected. Reason : {msg['text']}")
        else:
            if msg["event"] in Event.ALL:
                logging.warning(
                    f"Price updates messages with event {msg['event']} not supported by client"
                )
            else:
                logging.error(
                    f"Websocket returned a price update message with an unknown event {msg['event']}"
                )

    def _on_ticker_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Subscribed to the {msg['channel']} channel")
        elif "last_trade_price" in msg:
            self.tickers[msg["symbol"]] = msg["last_trade_price"]

    def _on_l2_updates(self, msg):
        symbol = msg["symbol"]

        if msg["event"] == Event.SNAPSHOT:
            # We should clear existing levels
            self.l2_book[symbol] = {Book.BID: sd(), Book.ASK: sd()}

        if msg["event"] in [Event.SNAPSHOT, Event.UPDATED]:
            for book in [Book.BID, Book.ASK]:
                updates = msg[book]
                for data in updates:

                    price = data["px"]
                    size = data["qty"]
                    if size == 0.0:
                        logging.info(f"removing {price}:{size}")
                        self.l2_book[symbol][book].pop(price)
                    else:
                        self.l2_book[symbol][book][price] = size

        if len(self.l2_book[symbol][Book.ASK]) > 0:
            logging.info(f"Ask: {self.l2_book[symbol][Book.ASK].peekitem(0)} ")
        if len(self.l2_book[symbol][Book.BID]) > 0:
            logging.info(f"Bid: {self.l2_book[symbol][Book.BID].peekitem(-1)}")

    def _on_l3_updates(self, msg):
        logging.info(msg)

    def _on_heartbeat_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Subscribed to the {msg['channel']} channel")
        elif msg["event"] == Event.UPDATED:
            pass
        else:
            pass

    def _on_auth_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            self.authenticated = True
        elif msg["event"] == Event.REJECTED:
            if self.authenticated:
                logging.warning("Trying To Authenticate while already authenticated")
                return
            raise ValueError("Failed to authenticate")

    def _on_balance_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Subscribed to the {msg['channel']} channel")
        elif msg["event"] == Event.SNAPSHOT:
            self.balances = parse_balance(msg["balances"])

    def _on_trading_updates(self, msg):
        """ Process message relating to trading activity"""
        if msg["event"] == Event.UPDATED:
            self._on_order_update(msg)
        elif msg["event"] == Event.SNAPSHOT:
            self._on_orders_snapshot(msg)
        elif msg["event"] == Event.REJECTED:
            self._on_order_rejection(msg)
        elif msg["event"] == Event.SUBSCRIBED:
            logging.info(f"Subscribed to the {msg['channel']} channel")
        else:
            if msg["event"] in Event.ALL:
                logging.warning(
                    f"Trading messages with event {msg['event']} not supported by client"
                )
            else:
                logging.error(
                    f"Websocket returned a trading message with an unknown event {msg['event']}"
                )

    def _on_order_update(self, msg):
        message = OrderResponse(msg)
        symbol = message.symbol
        self.open_orders[symbol][message.order_id] = message

        if message.order_status in OrderStatus.terminal_states():
            logging.info(f"Order in terminal state: {message.to_str()}")
            self.open_orders[symbol].pop(message.order_id)

    def _on_orders_snapshot(self, msg):
        """Snapshot of open orders - when we first subscribe to trading channel"""
        for mo in msg["orders"]:
            self._on_order_update(mo)

    def _on_order_rejection(self, msg):
        # TODO: handle outgoing orders - those without orderID yet
        logging.info(f"Removing {msg['orderID']} from open orders")
        logging.debug(msg)

    def cancel_order(self, order_id):
        return self.send_order(Order(OrderType.CANCEL, order_id=order_id))

    def cancel_all_orders(self):
        return self.send_order(Order(OrderType.CANCEL, order_id=-999))

    def send_order(self, order):
        """Send an order via the websocket

        Parameters
        ----------
        order : Order
            the order you want to send
        """
        if order.symbol not in self.symbols and order.order_id != -999:
            logging.error(
                f"[{order}] Sending orders for an symbol without subscribing to the market is not safe."
                f" You should subscribe first to symbol {order.symbol}"
            )
        else:
            self.send_force_order(order)

    def send_force_order(self, order):
        """Send an order via the websocket without checking basic tracking

        Parameters
        ----------
        order : Order
            the order you want to send
        """
        self.ws.send(json.dumps(order.order_to_dict()))

    @property
    def api_secret(self):
        """Api key required by the websocket

        if _api_secret is not None, it is taken from the environment variable BCEX_API_SECRET

        Returns
        -------
        str
        """
        return self._api_secret

    def _authenticate(self):
        auth_params = {
            "channel": "auth",
            "action": "subscribe",
            "token": self.api_secret,
        }
        self.ws.send(json.dumps(auth_params))
        self._wait_for_authentication()

    def _wait_for_authentication(self):
        """Waits until we have received message confirming authentication"""
        timeout = 50
        while not self.authenticated and timeout:
            time.sleep(0.1)
            timeout -= 1

        if not timeout:
            logging.error("Couldn't authenticate connection! Exiting.")
            raise webs.WebSocketTimeoutException(
                "Couldn't authenticate connection! Exiting."
            )

        logging.info("Successfully authenticated")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bcex_client = BcexClient(
        symbols=["BTC-USD", "ETH-BTC"],
        channels=["prices", "l2", "symbols"],
        channel_kwargs={"prices": {"granularity": 60}},
        env=Environment.STAGING,
    )

    bcex_client.connect()
    while True:
        time.sleep(1)
