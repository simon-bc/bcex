import logging
import random
import time
from copy import deepcopy

import numpy as np
from core.order_response import OrderStatus
from core.orders import Order, OrderSide, OrderType, TimeInForce
from core.symbol import Symbol
from core.websocket_client import BcexClient

order_quantity_map = {Symbol.ETHBTC: 2, Symbol.BTCUSD: 0.001}
increment_map = {Symbol.ETHBTC: 0.001, Symbol.BTCUSD: 1}
rounding_map = {Symbol.ETHBTC: 3, Symbol.BTCUSD: 0}


def main():
    sleep_time = 5
    levels = 5
    symbols = [Symbol.ETHBTC, Symbol.BTCUSD]
    merc_client = BcexClient(symbols=symbols)
    merc_client.connect()
    try:
        while True:
            time.sleep(sleep_time)
            for merid, status in deepcopy(merc_client.order_status).items():
                if status not in [
                    OrderStatus.REJECTED,
                    OrderStatus.EXPIRED,
                    OrderStatus.FILLED,
                    OrderStatus.CANCELLED,
                ]:
                    if random.random() > 0.4:
                        merc_client.send_order(
                            Order(OrderType.CANCEL, mercury_order_id=merid)
                        )
            for symbol in symbols:
                buy_price = merc_client.last_price.get(symbol, None)
                if buy_price is not None:
                    balance = merc_client.balances.get(symbol[-3:], {}).get(
                        "available", 0
                    )
                    if balance > 0:
                        for k in range(levels):

                            n = np.random.choice(20)
                            price = buy_price - n * increment_map[symbol]
                            price = round(price, rounding_map[symbol])

                            v = 1 + np.random.choice(5)
                            order_quantity = order_quantity_map[symbol] * v
                            o = Order(
                                OrderType.LIMIT,
                                symbol=symbol,
                                price=price,
                                side=OrderSide.BUY,
                                time_in_force=TimeInForce.GTC,
                                order_quantity=order_quantity,
                            )
                            logging.info(
                                "Sending Buy {} Limit at {} amount {}".format(
                                    symbol, price, order_quantity
                                )
                            )
                            merc_client.send_order(o)

                sell_price = merc_client.last_price.get(symbol, None)
                if sell_price is not None:
                    balance = merc_client.balances.get(symbol[:3], {}).get(
                        "available", 0
                    )
                    if balance > 0:
                        for k in range(levels):

                            n = np.random.choice(20)
                            price = sell_price + n * increment_map[symbol]
                            price = round(price, rounding_map[symbol])

                            v = 1 + np.random.choice(5)
                            order_quantity = order_quantity_map[symbol] * v
                            o = Order(
                                OrderType.LIMIT,
                                symbol=symb,
                                price=price,
                                side=OrderSide.SELL,
                                time_in_force=TimeInForce.GTC,
                                order_quantity=order_quantity,
                            )
                            logging.info(
                                "Sending Sell {} Limit at {} amount {}".format(
                                    symbol, price, order_quantity
                                )
                            )
                            logging.info(f"Order: {o.order_to_dict()}")
                            merc_client.send_order(o)

    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
