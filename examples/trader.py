from core.exchange_interface import ExchangeInterface
from core.websocket_client import Environment
import logging
import os
import sys


class BaseTrader:

    def __init__(self, symbol, api_key=None, env=Environment.STAGING):
        self.exchange = ExchangeInterface([symbol], api_key=api_key, env=env)
        self.exchange.connect()

        # TODO: might want to extend the cancellation of open orders to symbol specific?
        self.reset()

    def reset(self):
        logging.info("Cancelling all existing orders before moving forward")
        self.exchange.cancel_all_orders()

    def handle_orders(self):
        raise NotImplementedError("This should be implemented in subclass")

    def restart(self):
        # This is what bitmex one does - seems like it executes to whole script again - pretty cool?
        logging.warning("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def run_loop(self):
        while True:
            if not self.exchange.is_open():
                logging.error("Websocket has disconnected. Attempting to restart")
                self.restart()

            self.handle_orders()



class BasicLadderQuotes(BaseTrader):
    """Simple MM that places orders at regular intervals from last traded price"""

    def handle_orders(self):
        


