import logging
import random
import time
from copy import deepcopy
import numpy as np

from core.order_response import OrderStatus
from core.orders import Order, OrderSide, OrderType, TimeInForce
from core.websocket_client import MercuryClient

from customers_analytics.mercury.mercury_db_utils import Instrument

order_quantity_map = {Instrument.ETHBTC: 2, Instrument.BTCUSD: 0.001}
increment_map = {Instrument.ETHBTC: 0.001, Instrument.BTCUSD: 1}
rounding_map = {Instrument.ETHBTC: 3, Instrument.BTCUSD: 0}

def main():
    sleep_time = 5
    levels = 5
    instrs = [Instrument.ETHBTC, Instrument.BTCUSD]
    merc_client = MercuryClient(instruments=instrs)
    merc_client.run_websocket()
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
                        merc_client.send_order(Order(OrderType.CANCEL, mercury_order_id=merid))
            for instr in instrs:
                buy_price = merc_client.last_price.get(instr, None)
                if buy_price is not None:
                    balance = merc_client.balances.get(instr[-3:], {}).get("available", 0)
                    if balance > 0:
                        for k in range(levels):

                            n = np.random.choice(20)
                            price = buy_price  - n * increment_map[instr]
                            price = round(price, rounding_map[instr])

                            v = 1 + np.random.choice(5)
                            order_quantity = order_quantity_map[instr] * v
                            o = Order(
                                OrderType.LIMIT,
                                instrument=instr,
                                price=price,
                                side=OrderSide.BUY,
                                time_in_force=TimeInForce.GTC,
                                order_quantity=order_quantity,
                            )
                            logging.info(
                                "Sending Buy {} Limit at {} amount {}".format(instr, price, order_quantity)
                            )
                            merc_client.send_order(o)

                sell_price = merc_client.last_price.get(instr, None)
                if sell_price is not None:
                    balance = merc_client.balances.get(instr[:3], {}).get("available", 0)
                    if balance > 0:
                        for k in range(levels):

                            n = np.random.choice(20)
                            price = sell_price + n * increment_map[instr]
                            price = round(price, rounding_map[instr])

                            v = 1 + np.random.choice(5)
                            order_quantity = order_quantity_map[instr] * v
                            o = Order(
                                OrderType.LIMIT,
                                instrument=instr,
                                price=price,
                                side=OrderSide.SELL,
                                time_in_force=TimeInForce.GTC,
                                order_quantity=order_quantity,
                            )
                            logging.info(
                                "Sending Sell {} Limit at {} amount {}".format(instr, price, order_quantity)
                            )
                            logging.info(f"Order: {o.order_to_dict()}")
                            merc_client.send_order(o)

    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
