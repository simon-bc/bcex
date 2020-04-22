from core.orders import OrderSide


class Trade:
    def __init__(self, instrument, price, quantity, side, timestamp, trade_id=None):
        self.instrument = instrument
        self.price = price
        self.quantity = quantity
        if not OrderSide.is_valid(side):
            raise ValueError(f"Invalid trade side {side}")

        self.side = side
        self.timestamp = timestamp
        self.trade_id = trade_id

    @staticmethod
    def parse_from_msg(msg):
        instrument = msg["symbol"]
        price = float(msg["price"])
        quantity = float(msg["qty"])
        side = msg["side"]
        timestamp = msg["timestamp"]
        trade_id = msg.get("trade_id")

        return Trade(instrument, price, quantity, side, timestamp, trade_id)
