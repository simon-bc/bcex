import logging

from core.websocket_client import BcexClient
from examples.quote_both_sides import quote_randomly_both_sides

from customers_analytics.mercury.mercury_db_utils import Instrument

order_quantity_map = {Instrument.ETHBTC: 0.024, Instrument.BTCUSD: 0.001}


def main():
    try:
        bcex_client = BcexClient(instruments=[Instrument.ETHBTC, Instrument.BTCUSD])
        bcex_client.run_websocket()

        sleep_time = 5
        levels = 5

        quote_randomly_both_sides(bcex_client, levels, sleep_time)

    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
