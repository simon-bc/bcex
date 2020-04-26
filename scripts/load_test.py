import logging

from core.exchange_interface import ExchangeInterface
from core.symbol import Symbol
from core.websocket_client import Channel, Environment
from examples.quote_both_sides import quote_randomly_both_sides_interface
from websocket import WebSocketConnectionClosedException

order_quantity_map = {Symbol.ETHBTC: 0.024, Symbol.BTCUSD: 0.001}

RETRY_NUMBER = 5


def main():
    attempt_number = 1
    while attempt_number <= RETRY_NUMBER:
        try:
            ex_interface = ExchangeInterface(
                symbols=[Symbol.ETHBTC, Symbol.BTCUSD],
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
                env=Environment.STAGING,
            )

            sleep_time = 5
            levels = 5

            quote_randomly_both_sides_interface(ex_interface, levels, sleep_time)

        except WebSocketConnectionClosedException as e:
            logging.error(f"Attempt Number {attempt_number} errored with {e}")
            attempt_number += 1
        except Exception as e:
            raise e


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
