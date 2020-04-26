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
