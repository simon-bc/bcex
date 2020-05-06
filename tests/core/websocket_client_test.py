import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import pytz
from websocket import WebSocketTimeoutException

from bcex.core.symbol import Symbol
from bcex.core.websocket_client import (
    BcexClient,
    Channel,
    ChannelStatus,
    Event,
    Environment,
    Action,
)
from iso8601 import iso8601
from sortedcontainers import SortedDict


class TestChannel:
    @pytest.mark.parametrize(
        "channel, is_symbol_specific",
        [
            (Channel.HEARTBEAT, False),
            (Channel.SYMBOLS, True),
            (Channel.BALANCES, False),
            (Channel.AUTH, False),
            (Channel.PRICES, True),
            (Channel.TICKER, True),
            (Channel.TRADES, True),
            (Channel.L2, True),
            (Channel.L3, True),
            (Channel.TRADING, False),
            ("dymmy", None),
        ],
    )
    def test_is_symbol_specific(self, channel, is_symbol_specific):
        if is_symbol_specific is not None:
            assert Channel.is_symbol_specific(channel) == is_symbol_specific
        else:
            with pytest.raises(ValueError):
                Channel.is_symbol_specific(channel)


class TestBcexClient:
    @patch("bcex.core.websocket_client.BcexClient._init_channel_status")
    def test_init(self, mock_init_channel_status):
        mock_init_channel_status.return_value = Mock()
        client = BcexClient(
            symbols=[Symbol.ETHBTC, Symbol.BTCPAX],
            channels=None,
            channel_kwargs={
                Channel.TICKER: {"extra_dummy_ticket_arg": "dummy_val"},
                Channel.PRICES: {"granularity": 300},
            },
            env=Environment.STAGING,
            api_secret="dummy_key",
            cancel_position_on_exit=False,
        )
        assert client.symbols == [Symbol.ETHBTC, Symbol.BTCPAX]
        assert (
            client.channel_kwargs[Channel.TICKER]["extra_dummy_ticket_arg"]
            == "dummy_val"
        )
        assert client.channel_kwargs[Channel.PRICES]["granularity"] == 300
        # channel_kwargs might contain extra default kwargs

        assert client.api_secret == "dummy_key"
        assert client.ws_url == "wss://ws.staging.blockchain.info/mercury-gateway/v1/ws"
        assert client.origin == "https://pit.staging.blockchain.info"
        assert not client.cancel_position_on_exit

        assert mock_init_channel_status.call_count == 1

        client = BcexClient(
            symbols=[Symbol.ETHBTC, Symbol.BTCPAX],
            channels=None,
            channel_kwargs={
                Channel.TICKER: {"extra_dummy_ticket_arg": "dummy_val"},
                Channel.PRICES: {"granularity": 300},
            },
            env=Environment.PROD,
            api_secret="dummy_key",
            cancel_position_on_exit=False,
        )
        assert client.ws_url == "wss://ws.prod.blockchain.info/mercury-gateway/v1/ws"
        assert client.origin == "https://exchange.blockchain.com"
        with pytest.raises(ValueError):
            BcexClient(symbols=[Symbol.BTCUSD], env="dummy_env")

    @patch("bcex.core.websocket_client.threading")
    @patch("bcex.core.websocket_client.webs")
    def test_connect(self, mock_webs, mock_threading):
        ws_mock = Mock()
        thread_mock = Mock()
        thread_mock.start = Mock()
        thread_mock.daemon = False
        mock_webs.WebSocketApp = Mock(return_value=ws_mock)
        mock_threading.Thread = Mock(return_value=thread_mock)

        client = BcexClient(symbols=["BTC-USD"])
        client._subscribe_channels = Mock()
        client._wait_for_ws_connect = Mock()
        client.connect()

        assert mock_webs.WebSocketApp.call_count == 1
        assert mock_threading.Thread.call_count == 1

        assert client.wst == thread_mock
        assert client.wst.daemon is True
        assert client.wst.start.call_count == 1
        assert client._wait_for_ws_connect.call_count == 1
        assert client._subscribe_channels.call_count == 1

    def test_on_price_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        # error message
        msg = {
            "seqnum": 18,
            "event": "rejected",
            "channel": "prices",
            "text": "No granularity set",
        }
        client._on_price_updates(msg)

        msg = {
            "seqnum": 2,
            "event": "updated",
            "channel": "prices",
            "symbol": "BTC-USD",
            "price": [1559039640, 8697.24, 8700.98, 8697.27, 8700.98, 0.431],
        }

        client._on_price_updates(msg)

        assert client.candles["BTC-USD"] == [
            [1559039640, 8697.24, 8700.98, 8697.27, 8700.98, 0.431]
        ]

    def test_on_on_symbols_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        # error message
        msg = {
            "seqnum": 1,
            "event": "snapshot",
            "channel": "symbols",
            "symbol": "BTC-USD",
            "base_currency": "BTC",
            "base_currency_scale": 8,
            "counter_currency": "USD",
            "counter_currency_scale": 2,
            "min_price_increment": 10,
            "min_price_increment_scale": 0,
            "min_order_size": 50,
            "min_order_size_scale": 2,
            "max_order_size": 0,
            "max_order_size_scale": 8,
            "lot_size": 5,
            "lot_size_scale": 2,
            "status": "halt",
            "id": 1,
            "auction_price": 0.0,
            "auction_size": 0.0,
            "auction_time": "",
            "imbalance": 0.0,
        }
        client._on_symbols_updates(msg)

        assert client.symbol_details["BTC-USD"] == msg

        msg.update({"event": "updated"})

        client._on_symbols_updates(msg)

        assert client.symbol_details["BTC-USD"] == msg

    def test_on_market_trade_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 21,
            "event": "updated",
            "channel": "trades",
            "symbol": "BTC-USD",
            "timestamp": "2019-08-13T11:30:06.100140Z",
            "side": "sell",
            "qty": 8.5e-5,
            "price": 11252.4,
            "trade_id": "12884909920",
        }

        client._on_market_trade_updates(msg)

        trade = client.market_trades["BTC-USD"][0]
        assert trade.symbol == "BTC-USD"
        assert trade.quantity == 8.5e-5
        assert trade.side == "sell"
        assert trade.timestamp == "2019-08-13T11:30:06.100140Z"
        assert trade.trade_id == "12884909920"
        assert trade.price == 11252.4

    def test_on_l2_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 2,
            "event": "snapshot",
            "channel": "l2",
            "symbol": "BTC-USD",
            "bids": [
                {"px": 8723.45, "qty": 1.45, "num": 2},
                {"px": 8124.45, "qty": 123.45, "num": 1},
            ],
            "asks": [
                {"px": 8730.0, "qty": 1.55, "num": 2},
                {"px": 8904.45, "qty": 13.66, "num": 2},
            ],
        }
        client._on_l2_updates(msg)

        assert client.l2_book["BTC-USD"] == {
            "bids": SortedDict({8124.45: 123.45, 8723.45: 1.45}),
            "asks": SortedDict({8730.0: 1.55, 8904.45: 13.66}),
        }

        msg = {
            "seqnum": 3,
            "event": "updated",
            "channel": "l2",
            "symbol": "BTC-USD",
            "bids": [{"px": 8723.45, "qty": 1.1, "num": 1}],
            "asks": [],
        }

        client._on_l2_updates(msg)

        assert client.l2_book["BTC-USD"] == {
            "bids": SortedDict({8124.45: 123.45, 8723.45: 1.1}),
            "asks": SortedDict({8730.0: 1.55, 8904.45: 13.66}),
        }

        msg = {
            "seqnum": 3,
            "event": "updated",
            "channel": "l2",
            "symbol": "BTC-USD",
            "bids": [{"px": 8124.45, "qty": 0, "num": 1}],
            "asks": [],
        }

        client._on_l2_updates(msg)
        assert client.l2_book["BTC-USD"] == {
            "bids": SortedDict({8723.45: 1.1}),
            "asks": SortedDict({8730.0: 1.55, 8904.45: 13.66}),
        }

        msg = {
            "seqnum": 2,
            "event": "snapshot",
            "channel": "l2",
            "symbol": "BTC-USD",
            "bids": [{"px": 8723.45, "qty": 1.45, "num": 2}],
            "asks": [{"px": 8730.0, "qty": 1.55, "num": 2}],
        }
        client._on_l2_updates(msg)

        assert client.l2_book["BTC-USD"] == {
            "bids": SortedDict({8723.45: 1.45}),
            "asks": SortedDict({8730.0: 1.55}),
        }

    def test_on_heartbeat_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 1,
            "event": "updated",
            "channel": "heartbeat",
            "timestamp": "2019-05-31T08:36:45.666753Z",
        }

        client._on_heartbeat_updates(msg)

        assert client._last_heartbeat == iso8601.parse_date(
            "2019-05-31T08:36:45.666753Z"
        )

    def test_on_auth_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {"seqnum": 0, "event": "subscribed", "channel": "auth"}
        client._on_auth_updates(msg)
        assert client.authenticated

        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 0,
            "event": "rejected",
            "channel": "auth",
            "text": "Authentication Failed",
        }

        client._on_auth_updates(msg)

        assert client.channel_status["auth"] == ChannelStatus.REJECTED

    def test_on_balance_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 2,
            "event": "snapshot",
            "channel": "balances",
            "balances": [
                {
                    "currency": "BTC",
                    "balance": 0.00366963,
                    "available": 0.00266963,
                    "balance_local": 38.746779155,
                    "available_local": 28.188009155,
                    "rate": 10558.77,
                },
                {
                    "currency": "USD",
                    "balance": 11.66,
                    "available": 0.0,
                    "balance_local": 11.66,
                    "available_local": 0.0,
                    "rate": 1.0,
                },
                {
                    "currency": "ETH",
                    "balance": 0.18115942,
                    "available": 0.18115942,
                    "balance_local": 37.289855013,
                    "available_local": 37.289855013,
                    "rate": 205.84,
                },
            ],
            "total_available_local": 65.477864168,
            "total_balance_local": 87.696634168,
        }

        client._on_balance_updates(msg)

        assert client.balances == {
            "BTC": {"available": 0.00266963, "balance": 0.00366963},
            "USD": {"available": 0.0, "balance": 11.66},
            "ETH": {"available": 0.18115942, "balance": 0.18115942},
        }

    def test_on_trading_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        msg = {
            "seqnum": 3,
            "event": "snapshot",
            "channel": "trading",
            "orders": [
                {
                    "orderID": "12891851020",
                    "clOrdID": "78502a08-c8f1-4eff-b",
                    "symbol": "BTC-USD",
                    "side": "sell",
                    "ordType": "limit",
                    "orderQty": 5.0e-4,
                    "leavesQty": 5.0e-4,
                    "cumQty": 0.0,
                    "avgPx": 0.0,
                    "ordStatus": "open",
                    "timeInForce": "GTC",
                    "text": "New order",
                    "execType": "0",
                    "execID": "11321871",
                    "transactTime": "2019-08-13T11:30:03.000593290Z",
                    "msgType": 8,
                    "lastPx": 0.0,
                    "lastShares": 0.0,
                    "tradeId": "0",
                    "price": 15000.0,
                }
            ],
        }
        client._on_trading_updates(msg)

        order = client.open_orders["BTC-USD"]["12891851020"]

        assert order.client_order_id == "78502a08-c8f1-4eff-b"
        assert order.price == 15000
        assert order.order_quantity == 5.0e-4
        assert order.average_price == 0
        assert order.order_status == "open"

        msg = {
            "seqnum": 3,
            "event": "snapshot",
            "channel": "trading",
            "orders": [
                {
                    "orderID": "12891851020",
                    "clOrdID": "78502a08-c8f1-4eff-b",
                    "symbol": "BTC-USD",
                    "side": "sell",
                    "ordType": "limit",
                    "orderQty": 5.0e-4,
                    "leavesQty": 5.0e-4,
                    "cumQty": 0.0,
                    "avgPx": 0.0,
                    "ordStatus": "filled",
                    "timeInForce": "GTC",
                    "text": "New order",
                    "execType": "0",
                    "execID": "11321871",
                    "transactTime": "2019-08-13T11:30:03.000593290Z",
                    "msgType": 8,
                    "lastPx": 0.0,
                    "lastShares": 0.0,
                    "tradeId": "0",
                    "price": 15000.0,
                }
            ],
        }

        client._on_trading_updates(msg)

        assert client.open_orders["BTC-USD"].get("12891851020") is None

    def test_on_ticker_updates(self):
        client = BcexClient(symbols=["BTC-USD"])

        # snapshot event - with last_trade_price
        msg_1 = {
            "seqnum": 1,
            "event": "snapshot",
            "channel": "ticker",
            "symbol": "BTC-USD",
            "price_24h": 7500.0,
            "volume_24h": 0.0141,
            "last_trade_price": 7499.0,
        }
        client._on_ticker_updates(msg_1)
        assert client.tickers["BTC-USD"]["price_24h"] == 7500.0
        assert client.tickers["BTC-USD"]["volume_24h"] == 0.0141
        assert (
            client.tickers["BTC-USD"]["last_trade_price"] == 7499.0
        )  # from previous update

        # updated event - no last_trade_price
        msg_2 = {
            "seqnum": 24,
            "event": "updated",
            "channel": "ticker",
            "symbol": "BTC-USD",
            "price_24h": 7500.1,
            "volume_24h": 0.0142,
        }
        client._on_ticker_updates(msg_2)
        assert client.tickers["BTC-USD"]["price_24h"] == 7500.1
        assert client.tickers["BTC-USD"]["volume_24h"] == 0.0142
        assert (
            client.tickers["BTC-USD"]["last_trade_price"] == 7499.0
        )  # from previous update

    def test_on_unsupported_event_message(self):
        client = BcexClient([Symbol.ALGOUSD])
        client._on_unsupported_event_message(
            {"event": Event.SNAPSHOT}, Channel.HEARTBEAT
        )
        client._on_unsupported_event_message(
            {"event": "dummy_event"}, Channel.HEARTBEAT
        )

    def test_on_message_unsupported(self):
        client = BcexClient([Symbol.ALGOUSD])
        client._on_message_unsupported({"channel": Event.SNAPSHOT})
        client._on_message_unsupported({"channel": "dummy_channel"})

    def test_on_message(self):
        client = BcexClient([Symbol.ALGOUSD])
        client._check_message_seqnum = Mock()
        channels = [
            "dummy_channel",
            Channel.TRADES,
            Channel.TICKER,
            Channel.PRICES,
            Channel.AUTH,
            Channel.BALANCES,
            Channel.HEARTBEAT,
            Channel.SYMBOLS,
            Channel.L2,
            Channel.L3,
        ]

        # set up the mocks
        mocks = [Mock() for _ in range(len(channels))]
        client._on_message_unsupported = mocks[0]
        client._on_market_trade_updates = mocks[1]
        client._on_ticker_updates = mocks[2]
        client._on_price_updates = mocks[3]
        client._on_auth_updates = mocks[4]
        client._on_balance_updates = mocks[5]
        client._on_heartbeat_updates = mocks[6]
        client._on_symbols_updates = mocks[7]
        client._on_l2_updates = mocks[8]
        client._on_l3_updates = mocks[9]

        # checks
        msg = {}
        for i, ch in enumerate(channels):
            msg.update({"channel": ch})
            client.on_message(json.dumps(msg))
            assert client._check_message_seqnum.call_count == i + 1
            for j in range(i):
                assert mocks[j].call_count == 1
            for j in range(i + 1, len(channels)):
                assert mocks[j].call_count == 0
            assert mocks[i].call_args[0][0] == msg

        client.on_message(None)

    def test_seqnum(self):
        # first message should be 0
        client = BcexClient([Symbol.ALGOUSD])
        client.exit = Mock()
        client._on_heartbeat_updates = Mock()
        assert client._seqnum == -1

        client.on_message(json.dumps({"seqnum": 0, "channel": Channel.HEARTBEAT}))
        assert client.exit.call_count == 0

        # if first message is not 0 it exits
        client = BcexClient([Symbol.ALGOUSD])
        client.exit = Mock()
        client._on_heartbeat_updates = Mock()

        client.on_message(json.dumps({"seqnum": 1, "channel": Channel.HEARTBEAT}))
        assert client.exit.call_count == 1

        # if one message has not been received it exits
        client = BcexClient([Symbol.ALGOUSD])
        client.exit = Mock()
        client._on_heartbeat_updates = Mock()

        client.on_message(json.dumps({"seqnum": 0, "channel": Channel.HEARTBEAT}))
        client.on_message(json.dumps({"seqnum": 1, "channel": Channel.HEARTBEAT}))
        client.on_message(json.dumps({"seqnum": 2, "channel": Channel.HEARTBEAT}))
        client.on_message(json.dumps({"seqnum": 3, "channel": Channel.HEARTBEAT}))
        assert client.exit.call_count == 0
        client.on_message(json.dumps({"seqnum": 5, "channel": Channel.HEARTBEAT}))
        assert client.exit.call_count == 1

    @patch("bcex.core.websocket_client.datetime")
    def test_on_ping_checks_heartbeat(self, mock_datetime):
        client = BcexClient([Symbol.ALGOUSD])
        client.exit = Mock()
        # initially we do not have a heartbeat reference
        assert client._last_heartbeat is None

        # if no heartbeats subscribed we ignore it
        dt0 = datetime(2017, 1, 2, 1, tzinfo=pytz.UTC)
        mock_datetime.now = Mock(return_value=dt0)
        client.on_ping()
        assert client._last_heartbeat is None
        assert mock_datetime.now.call_count == 0
        assert client.exit.call_count == 0

        # heartbeats subscribed will initiate the last heartbeat reference
        client.channel_status[Channel.HEARTBEAT] = ChannelStatus.SUBSCRIBED
        client.on_ping()
        assert client._last_heartbeat == dt0
        assert mock_datetime.now.call_count == 1
        assert client.exit.call_count == 0

        # last heartbeat request was less than 5 seconds ago
        mock_datetime.now = Mock(return_value=dt0 + timedelta(seconds=2))
        client.on_ping()
        assert client._last_heartbeat == dt0
        assert mock_datetime.now.call_count == 1
        assert client.exit.call_count == 0

        # last heartbeat request was between 5 and 10 seconds ago
        mock_datetime.now = Mock(return_value=dt0 + timedelta(seconds=7))
        client.on_ping()
        assert client._last_heartbeat == dt0
        assert mock_datetime.now.call_count == 1
        assert client.exit.call_count == 0

        # last heartbeat request was more than 10 seconds ago : we exit
        mock_datetime.now = Mock(return_value=dt0 + timedelta(seconds=13))
        client.on_ping()
        assert mock_datetime.now.call_count == 1
        assert client.exit.call_count == 1

    def test_subscribe_channels(self):
        client = BcexClient(
            [Symbol.ETHBTC, Symbol.ALGOUSD],
            channels=[Channel.HEARTBEAT, Channel.SYMBOLS],
            api_secret="my_api_key",
        )
        client._public_subscription = Mock()
        client._private_subscription = Mock()
        client._subscribe_channels()

        assert client._public_subscription.call_count == 1
        assert client._private_subscription.call_count == 1

        client._api_secret = None
        client._subscribe_channels()
        assert client._public_subscription.call_count == 2
        assert client._private_subscription.call_count == 1

    def test_public_subscriptions(self):
        client = BcexClient(
            [Symbol.ETHBTC, Symbol.ALGOUSD],
            channels=[Channel.HEARTBEAT, Channel.SYMBOLS],
            channel_kwargs={
                Channel.SYMBOLS: {"dummy_arg": "dummy_val"},
                Channel.HEARTBEAT: {"t": 5},
            },
        )
        client._wait_for_confirmation = Mock()  # will test separately

        ws_mock = Mock()
        ws_mock.send = Mock()
        client.ws = ws_mock

        client._public_subscription()
        assert ws_mock.send.call_count == 3  # 2 for the 2 symbols and 1 for heartbeat
        subscriptions = [args[0][0] for args in ws_mock.send.call_args_list]
        assert set(subscriptions) == {
            json.dumps(
                {
                    "action": Action.SUBSCRIBE,
                    "channel": Channel.SYMBOLS,
                    "symbol": Symbol.ALGOUSD,
                    "dummy_arg": "dummy_val",
                }
            ),
            json.dumps(
                {
                    "action": Action.SUBSCRIBE,
                    "channel": Channel.SYMBOLS,
                    "symbol": Symbol.ETHBTC,
                    "dummy_arg": "dummy_val",
                }
            ),
            json.dumps(
                {"action": Action.SUBSCRIBE, "channel": Channel.HEARTBEAT, "t": 5}
            ),
        }

        assert (
            client.channel_status[Channel.HEARTBEAT]
            == ChannelStatus.WAITING_CONFIRMATION
        )
        assert (
            client.channel_status[Channel.SYMBOLS][Symbol.ETHBTC]
            == ChannelStatus.WAITING_CONFIRMATION
        )
        assert (
            client.channel_status[Channel.SYMBOLS][Symbol.ALGOUSD]
            == ChannelStatus.WAITING_CONFIRMATION
        )

        # make sure we will wait for the correct channels
        assert client._wait_for_confirmation.call_count == 1
        assert set(client._wait_for_confirmation.call_args[0][0]) == {
            (Channel.HEARTBEAT, None),
            (Channel.SYMBOLS, Symbol.ETHBTC),
            (Channel.SYMBOLS, Symbol.ALGOUSD),
        }

    def test_private_subscriptions(self):
        client = BcexClient(
            [Symbol.ETHBTC, Symbol.ALGOUSD],
            channels=[Channel.TRADING],
            api_secret="my_api_tokennn",
        )
        client._wait_for_confirmation = Mock()  # will test separately
        client._wait_for_authentication = Mock()  # will test separately

        ws_mock = Mock()
        ws_mock.send = Mock()
        client.ws = ws_mock

        client._private_subscription()
        assert ws_mock.send.call_count == 2  # one for authentication, one for channel

        # auth message sent
        auth = ws_mock.send.call_args_list[0][0][0]
        assert auth == json.dumps(
            {
                "channel": Channel.AUTH,
                "action": Action.SUBSCRIBE,
                "token": "my_api_tokennn",
            }
        )

        # subscription channel message sent
        subscriptions = ws_mock.send.call_args_list[1][0][0]
        assert subscriptions == json.dumps(
            {"action": Action.SUBSCRIBE, "channel": Channel.TRADING}
        )

        assert (
            client.channel_status[Channel.TRADING] == ChannelStatus.WAITING_CONFIRMATION
        )

        # make sure we will wait for the correct channels
        assert client._wait_for_confirmation.call_count == 1
        assert client._wait_for_authentication.call_count == 1

        assert set(client._wait_for_confirmation.call_args[0][0]) == {
            (Channel.TRADING, None)
        }

    @patch("bcex.core.websocket_client.time")
    def test_wait_for_authentication(self, mock_time):
        mock_time.sleep = Mock()
        client = BcexClient(
            [Symbol.ETHBTC, Symbol.ALGOUSD],
            channels=[Channel.TRADING],
            api_secret="my_api_tokennn",
        )
        client.channel_status[Channel.AUTH] = ChannelStatus.UNSUBSCRIBED
        with pytest.raises(WebSocketTimeoutException):
            client._wait_for_authentication()

        assert mock_time.sleep.call_count >= 1

        mock_time.sleep.reset_mock()

        client.channel_status[Channel.AUTH] = ChannelStatus.SUBSCRIBED
        client._wait_for_authentication()
        assert mock_time.sleep.call_count == 0

    @patch("bcex.core.websocket_client.time")
    def test_send_subscriptions_to_ws(self, mock_time):
        mock_time.sleep = Mock()

        channels = [Channel.HEARTBEAT, Channel.SYMBOLS]
        client = BcexClient([Symbol.ETHBTC, Symbol.ALGOUSD], channels=channels)
        subscriptions = [
            (Channel.HEARTBEAT, None),
            (Channel.SYMBOLS, Symbol.ETHBTC),
            (Channel.SYMBOLS, Symbol.ALGOUSD),
        ]
        client.channel_status[Channel.HEARTBEAT] = ChannelStatus.WAITING_CONFIRMATION
        client.channel_status[Channel.SYMBOLS][
            Symbol.ETHBTC
        ] = ChannelStatus.WAITING_CONFIRMATION
        client.channel_status[Channel.SYMBOLS][
            Symbol.ALGOUSD
        ] = ChannelStatus.WAITING_CONFIRMATION

        client._wait_for_confirmation(subscriptions)
        assert mock_time.sleep.call_count == 5

        mock_time.sleep.reset_mock()
        client.channel_status[Channel.HEARTBEAT] = ChannelStatus.SUBSCRIBED
        client.channel_status[Channel.SYMBOLS][
            Symbol.ALGOUSD
        ] = ChannelStatus.SUBSCRIBED
        client._wait_for_confirmation(subscriptions)
        assert mock_time.sleep.call_count == 5

        mock_time.sleep.reset_mock()
        client.channel_status[Channel.SYMBOLS][Symbol.ETHBTC] = ChannelStatus.SUBSCRIBED
        client._wait_for_confirmation(subscriptions)
        assert mock_time.sleep.call_count == 1
