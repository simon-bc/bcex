from unittest.mock import Mock

from core.websocket_client import BcexClient


class TestBcexClientPriceUpdates(object):
    def test_on_price_updates(self):
        client = BcexClient(Mock())

        # error message
        msg = {
            "seqnum": 18,
            "event": "rejected",
            "channel": "prices",
            "text": "No granularity set",
        }
        client._on_price_updates(msg)

    def test_on_ticker_updates(self):
        client = BcexClient(Mock())

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
