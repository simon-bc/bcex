import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
import websocket as webs
from bcex.core.order_response import OrderResponse, OrderStatus
from bcex.core.orders import Order, OrderType
from bcex.core.trade import Trade
from bcex.core.utils import update_max_list, valid_datetime
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

    @staticmethod
    def is_symbol_specific(channel):
        """Whether the channel is symbol specific
        """
        if channel in [
            Channel.AUTH,
            Channel.HEARTBEAT,
            Channel.TRADING,
            Channel.BALANCES,
        ]:
            return False
        elif channel in [
            Channel.L2,
            Channel.L3,
            Channel.PRICES,
            Channel.SYMBOLS,
            Channel.TICKER,
            Channel.TRADES,
        ]:
            return True
        else:
            raise ValueError(f"Unexpected channel {channel}")


class Event:
    """Indicate the purpose of the message
    """

    UPDATED = "updated"  # An update corresponding to the channel has occurred
    SNAPSHOT = "snapshot"  # A channel snapshot has been provided
    REJECTED = "rejected"  # the last action for the channel was rejected
    SUBSCRIBED = "subscribed"  # The channel was successfully subscribed to
    UNSUBSCRIBED = "unsubscribed"  # The channel was successfully unsubscribed to

    ALL = [UPDATED, SNAPSHOT, REJECTED, SUBSCRIBED, UNSUBSCRIBED]


class ChannelStatus:
    """Indicates the status of the channels subscriptions
    """

    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    WAITING_CONFIRMATION = "waiting_confirmation"
    REJECTED = "rejected"


class BcexClient(object):
    """Blockchain.com Exchange Websocket API client v1

    Attributes
    ----------
    balances : dict
    open_orders : dict
    channel_status: dict
        keeps track of the status of each subscription using ChannelStatus
        keys are channels, str from the enum Channel.
         - for symbol specific channels, the value is a dict with key the symbol, str from the enum Symbol
            and value the status, str from the enum ChannelStatus
         - for non-symbol specific channels, the value is the status, str from the enum ChannelStatus
    tickers: dict
    ws: WebSocketClient
    wst: Thread
        websocket client thread
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
        env=Environment.PROD,
        api_secret=None,
        cancel_position_on_exit=True,
    ):
        """This class connects to the Blockchain.com Exchange websocket client

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
            api secret for the exchange which can be obtained once logged in, in settings (click on username) > Api
            if not provided, the api secret will be taken from environment variable BCEX_API_SECRET
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
        self.ws_url = ws_url
        self.origin = origin_url
        self.exited = False

        self.symbols = symbols
        self.symbol_details = {s: {} for s in symbols}

        self.channels = channels or list(
            set(Channel.ALL) - {Channel.L3}
        )  # L3 not handled yet
        # default channel_kwargs
        self.channel_kwargs = {Channel.PRICES: {"granularity": 60}}
        self._update_default_channel_kwargs(channel_kwargs)

        self.channel_status = None

        # webs.enableTrace(True)
        self.ws = None
        self.wst = None

        self._api_secret = api_secret

        if api_secret is None and "BCEX_API_SECRET" in os.environ:
            self._api_secret = os.environ["BCEX_API_SECRET"]

        # use these dictionaries to store the data we receive
        self.balances = {}
        self.tickers = defaultdict(dict)

        self.l2_book = {}
        for symbol in self.symbols:
            self.l2_book[symbol] = {"bids": sd(), "asks": sd()}

        self.candles = defaultdict(list)
        self.market_trades = defaultdict(list)
        self.open_orders = defaultdict(dict)

        # check health of the websocket
        self._seqnum = -1  # higher seqnum that we received (usually the latest)
        self._last_heartbeat = None

        # set initial status to unsubscribed
        self._init_channel_status()

    def _update_default_channel_kwargs(self, channel_kwargs):
        # override channel_kwargs with specified channel_kwargs
        if channel_kwargs is not None:
            for ch, kw in channel_kwargs.items():
                if ch not in self.channel_kwargs:
                    self.channel_kwargs[ch] = {}
                self.channel_kwargs[ch].update(kw)

    def _init_channel_status(self):
        """Initialise or reset channel status
        """
        self.channel_status = {}

        for channel in Channel.ALL:
            if Channel.is_symbol_specific(channel):
                self.channel_status[channel] = {
                    s: ChannelStatus.UNSUBSCRIBED for s in self.symbols
                }
            else:
                self.channel_status[channel] = ChannelStatus.UNSUBSCRIBED

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

    @property
    def authenticated(self):
        return (
            self.channel_status.get(Channel.AUTH, ChannelStatus.UNSUBSCRIBED)
            == ChannelStatus.SUBSCRIBED
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
        channels = set(self.channels).intersection(set(Channel.PUBLIC))
        subscriptions_to_check = self._send_subscriptions_to_ws(channels)
        self._wait_for_confirmation(subscriptions_to_check)

    def _send_subscriptions_to_ws(self, channels):
        subscriptions_to_check = []
        for channel in channels:
            kwargs = self.channel_kwargs.get(channel)
            if Channel.is_symbol_specific(channel):
                for symbol in self.symbols:
                    subscription = {
                        "action": Action.SUBSCRIBE,
                        "channel": channel,
                        "symbol": symbol,
                    }
                    if kwargs:
                        subscription.update(kwargs)
                    self.channel_status[channel][
                        symbol
                    ] = ChannelStatus.WAITING_CONFIRMATION
                    logging.info(subscription)
                    self.ws.send(json.dumps(subscription))
                    subscriptions_to_check.append((channel, symbol))
            else:
                subscription = {"action": Action.SUBSCRIBE, "channel": channel}
                if kwargs:
                    subscription.update(kwargs)
                logging.info(subscription)
                self.channel_status[channel] = ChannelStatus.WAITING_CONFIRMATION
                self.ws.send(json.dumps(subscription))
                subscriptions_to_check.append((channel, None))
        return subscriptions_to_check

    def _wait_for_confirmation(self, subscriptions_to_check):
        all_answered = False
        conn_timeout = 5
        while not all_answered and conn_timeout:
            time.sleep(1)
            conn_timeout -= 1
            all_answered = True
            for channel, symbol in subscriptions_to_check:
                if self.check_channel_status(
                    ChannelStatus.WAITING_CONFIRMATION, channel, symbol
                ):
                    all_answered = False
                    break

        if not all_answered:
            logging.warning("Could not subscribe to all channels")

    def check_channel_status(self, status, channel, symbol=None):
        if symbol is None:
            return self.channel_status[channel] == status
        else:
            return self.channel_status[channel][symbol] == status

    def _private_subscription(self):
        self._authenticate()
        channels = set(self.channels).intersection(set(Channel.PRIVATE))
        channels = channels - {Channel.AUTH}  # already subscribed
        subscriptions_to_check = self._send_subscriptions_to_ws(channels)
        self._wait_for_confirmation(subscriptions_to_check)

    def connect(self):
        """Connects to the websocket and runs it
        """
        self.ws = webs.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
            on_ping=self.on_ping,
        )
        self.wst = threading.Thread(
            target=lambda: self.ws.run_forever(origin=self.origin, ping_interval=5)
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
        if self.cancel_position_on_exit and self.authenticated:
            logging.info(f"Cancelling all orders before exiting")
            self.cancel_all_orders()
        self._init_channel_status()
        logging.warning("\n-- Websocket Closed --")

    def on_error(self, error):
        """On error websocket connection
        """
        self._on_error(error)

    def _on_error(self, err):
        self._error = err
        logging.error(err)
        self.exit()

    def on_ping(self, *args):
        """On ping interval from WebSocket Client.

        This checks health of the websocket on a regular basis

        Parameters
        ----------
        args : list
            unused
        """
        if self.channel_status[Channel.HEARTBEAT] != ChannelStatus.SUBSCRIBED:
            return
        now = datetime.now(pytz.UTC)
        if self._last_heartbeat is None:
            self._last_heartbeat = now
        log_heartbeat = f"[{now}] Last heartbeat was {(now - self._last_heartbeat).total_seconds()} seconds ago."
        if now - self._last_heartbeat > timedelta(seconds=10):
            logging.error(log_heartbeat + " Exiting")
            self.exit()
        elif (
            timedelta(seconds=10) >= now - self._last_heartbeat >= timedelta(seconds=5)
        ):
            logging.warning(log_heartbeat + " Waiting few more seconds")
        else:
            logging.debug(log_heartbeat)

    def exit(self):
        """On exit websocket connection
        """
        self.exited = True
        self.ws.close()

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
        self._check_message_seqnum(msg)

        logging.debug(msg)

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
            self._on_market_trade_updates(msg)
        elif msg["channel"] == Channel.SYMBOLS:
            self._on_symbols_updates(msg)
        else:
            self._on_message_unsupported(msg)

    def _check_message_seqnum(self, msg):
        """Checks that the messages received by the client increment by one

        Notes
        -----
        If the client receives a seqnum which has skipped one or more sequences, it indicates that a message was missed
        and the client is recommended to restart the websocket connection.
        """
        if "seqnum" not in msg:
            logging.error(f"seqnum missing from msg {msg}")
            return

        seqnum = msg["seqnum"]
        if seqnum > self._seqnum + 1:
            self._seqnum = seqnum
            logging.error(
                f"Missing messages with seqnums between {self._seqnum + 1} and {seqnum - 1} : Exiting"
            )
            self.exit()
        elif seqnum < self._seqnum + 1:
            logging.warning(f"Received with delay message with seqnum {seqnum}")
        else:
            self._seqnum = seqnum

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
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.SNAPSHOT:
            # has only one symbol per message unlike the documentation
            symbol = msg["symbol"]
            self.symbol_details.update({symbol: msg})
        elif msg["event"] == Event.UPDATED:
            # TODO: should we drop the extra info
            symbol = msg["symbol"]
            self.symbol_details[symbol].update(msg)
        else:
            self._on_unsupported_event_message(msg, Channel.SYMBOLS)

    def _on_market_trade_updates(self, msg):
        """Handle market trades by appending to symbol trade history"""
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.UPDATED:
            symbol = msg["symbol"]
            trades = self.market_trades[symbol]
            trade = Trade.parse_from_msg(msg)
            self.market_trades[symbol] = update_max_list(
                trades, trade, self.MAX_TRADES_LEN
            )
        else:
            self._on_unsupported_event_message(msg, Channel.TRADES)

    def _on_price_updates(self, msg):
        """Store latest candle update and truncate list to length MAX_CANDLES_LEN"""
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.UPDATED:
            key = msg["symbol"]
            if "price" in msg:
                candles = self.candles[key]
                self.candles[key] = update_max_list(
                    candles, msg["price"], self.MAX_CANDLES_LEN
                )
            else:
                logging.warning(f"Received a price update without price information")
        elif msg["event"] == Event.REJECTED:
            self._on_rejected_subscription_updates(msg)
        else:
            self._on_unsupported_event_message(msg, Channel.PRICES)

    def _on_subscribed_updates(self, msg):
        """When receiving an message about a confirmed subscription

        Updates the internal attributes to keep track of what channels are subscribed to
        """
        channel = msg["channel"]
        log = f"Successfully subscribed to channel {channel}"
        if "symbol" in msg:
            symbol = msg["symbol"]
            log = f"[{symbol}] " + log
            self.channel_status[channel][symbol] = ChannelStatus.SUBSCRIBED
        else:
            self.channel_status[channel] = ChannelStatus.SUBSCRIBED
        logging.info(log)

    def _on_rejected_subscription_updates(self, msg):
        """When receiving an message about a rejected subscription

        Updates the internal attributes to keep track of what channels are subscribed to
        """
        channel = msg["channel"]
        log = f"Subscription to channel {channel} rejected. Reason : {msg.get('text', 'Not Provided')}"
        if "symbol" in msg:
            symbol = msg["symbol"]
            log = f"[{symbol}] " + log
            self.channel_status[channel][symbol] = ChannelStatus.REJECTED
        else:
            self.channel_status[channel] = ChannelStatus.REJECTED
        logging.warning(log)

    def _on_unsupported_event_message(self, msg, channel):
        if msg["event"] in Event.ALL:
            logging.warning(
                f"Message updates from channel {channel} with event {msg['event']} not supported by client"
            )
        else:
            logging.error(
                f"Websocket returned a {channel} update message with an unknown event {msg['event']}"
            )

    def _on_ticker_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] in [Event.SNAPSHOT, Event.UPDATED]:
            # last_trade_price not always present
            for k in ["last_trade_price", "price_24h", "volume_24h"]:
                if k in msg:
                    self.tickers[msg["symbol"]].update({k: msg[k]})
        else:
            self._on_unsupported_event_message(msg, Channel.TICKER)

    def _on_l2_updates(self, msg):
        symbol = msg["symbol"]

        if msg["event"] == Event.SNAPSHOT:
            # We should clear existing levels
            self.l2_book[symbol] = {Book.BID: sd(), Book.ASK: sd()}
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] in [Event.SNAPSHOT, Event.UPDATED]:
            for book in [Book.BID, Book.ASK]:
                updates = msg[book]
                for data in updates:

                    price = data["px"]
                    size = data["qty"]
                    if size == 0.0:
                        logging.debug(f"removing {price}:{size}")
                        self.l2_book[symbol][book].pop(price)
                    else:
                        self.l2_book[symbol][book][price] = size
        else:
            self._on_unsupported_event_message(msg, Channel.L2)

        if len(self.l2_book[symbol][Book.ASK]) > 0:
            logging.debug(f"Ask: {self.l2_book[symbol][Book.ASK].peekitem(0)} ")
        if len(self.l2_book[symbol][Book.BID]) > 0:
            logging.debug(f"Bid: {self.l2_book[symbol][Book.BID].peekitem(-1)}")

    def _on_l3_updates(self, msg):
        logging.debug(msg)

    def _on_heartbeat_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.UPDATED:
            self._last_heartbeat = valid_datetime(msg["timestamp"])
            logging.debug(f"Updated last heartbeat to {self._last_heartbeat}")
        else:
            self._on_unsupported_event_message(msg, Channel.HEARTBEAT)

    def _on_auth_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.REJECTED:
            if self.authenticated:
                logging.warning("Trying To Authenticate while already authenticated")
                return
            self._on_rejected_subscription_updates(msg)
        else:
            self._on_unsupported_event_message(msg, Channel.AUTH)

    def _on_balance_updates(self, msg):
        if msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        elif msg["event"] == Event.SNAPSHOT:
            self.balances = {
                b["currency"]: {"available": b["available"], "balance": b["balance"]}
                for b in msg["balances"]
            }
        else:
            self._on_unsupported_event_message(msg, Channel.BALANCES)

    def _on_trading_updates(self, msg):
        """Process message relating to trading activity"""
        if msg["event"] == Event.UPDATED:
            self._on_order_update(msg)
        elif msg["event"] == Event.SNAPSHOT:
            self._on_orders_snapshot(msg)
        elif msg["event"] == Event.REJECTED:
            self._on_order_rejection(msg)
        elif msg["event"] == Event.SUBSCRIBED:
            self._on_subscribed_updates(msg)
        else:
            self._on_unsupported_event_message(msg, Channel.TRADING)

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
        if self.channel_status[Channel.TRADING] == ChannelStatus.SUBSCRIBED:
            # TODO: handle outgoing orders - those without orderID yet
            logging.info(f"Removing {msg['orderID']} from open orders")
        else:
            self._on_rejected_subscription_updates(msg)

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


class MockBcexClient(BcexClient):
    """Mock Bcex Client which does not actually connects to the websocket
    """

    def connect(self):
        pass

    def close(self):
        pass

    def exit(self):
        pass


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
