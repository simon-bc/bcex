import logging

from core.exchange_interface import ExchangeInterface
from core.websocket_client import BcexClient, Channel
from examples.quote_both_sides import quote_randomly_both_sides_interface

from customers_analytics.mercury.mercury_db_utils import Instrument

order_quantity_map = {Instrument.ETHBTC: 0.024, Instrument.BTCUSD: 0.001}


def main():
    try:
        ex_interface = ExchangeInterface(
            instruments=[Instrument.ETHBTC, Instrument.BTCUSD],
            channels=[
                Channel.HEARTBEAT,
                Channel.L2,
                Channel.PRICES,
                Channel.SYMBOLS,
                Channel.TICKER,
                Channel.TRADES,
                Channel.AUTH,
                Channel.BALANCES,
                Channel.TRADING,
            ],
        )

        sleep_time = 5
        levels = 5

        quote_randomly_both_sides_interface(ex_interface, levels, sleep_time)

    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
