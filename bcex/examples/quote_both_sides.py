import logging
import random
import time

from bcex.core.bcex_interface import BcexInterface
from bcex.core.order_response import OrderStatus
from bcex.core.orders import OrderSide, OrderType, TimeInForce
from bcex.core.symbol import Symbol

ORDER_QUANTITY_MAP = {Symbol.ETHBTC: 0.024, Symbol.BTCUSD: 0.001}


def quote_randomly_both_sides_interface(
    ex_interface: BcexInterface, levels, sleep_time
):
    """
    Parameters
    ----------
    bcex_client: BcexInterface
    levels: int
        levels of the orderbooks to populate
    sleep_time: int
        waiting time between each order updates in seconds
    """
    ex_interface.connect()

    time.sleep(sleep_time)
    ex_interface.cancel_all_orders()

    while True:
        time.sleep(sleep_time)

        # Randomly cancel existing open orders
        for clordid, order in ex_interface.get_all_open_orders(to_dict=False).items():
            # if isinstance(order, Order):
            #     # exchange has not updated us on this order yet
            #     continue

            if order.order_status not in OrderStatus.terminal_states():
                if random.random() > 0.4:
                    ex_interface.cancel_order(order_id=order.order_id)
        for symbol in ex_interface.get_symbols():

            last_trade_price = ex_interface.get_last_traded_price(symbol)
            logging.info(f"Last Traded price {last_trade_price}")
            if last_trade_price:
                balance_coin = symbol.split("-")[1]
                balance = ex_interface.get_available_balance(balance_coin)
                logging.info(f"Balance {balance} {balance_coin}")
                if balance > 0:
                    for k in range(levels):
                        i = 1 + (k + 1) / 1000 + (random.random() - 0.5) / 1000
                        price = float(last_trade_price) / i
                        order_quantity = min(max(balance / (price), 10 / price), 0.01)
                        ex_interface.place_order(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            quantity=order_quantity,
                            price=price,
                            order_type=OrderType.LIMIT,
                            time_in_force=TimeInForce.GTC,
                            check_balance=True,
                        )
                        logging.info(
                            "Sending Buy Limit at {} amount {}".format(
                                price, order_quantity
                            )
                        )

                balance_coin = symbol.split("-")[0]
                balance = ex_interface.get_available_balance(balance_coin)
                logging.info(f"Balance {balance} {balance_coin}")
                if balance > 0:
                    for k in range(levels):
                        i = 1 - (k + 1) / 1000 + (random.random() - 0.5) / 1000
                        price = round(float(last_trade_price / i), 0)
                        order_quantity = min(round(balance / 10, 6), 0.01)
                        ex_interface.place_order(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=order_quantity,
                            price=price,
                            order_type=OrderType.LIMIT,
                            time_in_force=TimeInForce.GTC,
                            check_balance=True,
                        )
                        logging.info(
                            "Sending Sell Limit at {} amount {}".format(
                                price, order_quantity
                            )
                        )
