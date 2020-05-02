from bcex.core.orders import OrderSide


class Trade:
    """
    Attributes
    ----------
    symbol: str from enum Symbol
    price: float
    quantity: float
    side: str from enum OrderSide
    timestamp: str
    trade_id: str
    """

    def __init__(self, symbol, price, quantity, side, timestamp, trade_id=None):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        if not OrderSide.is_valid(side):
            raise ValueError(f"Invalid trade side {side}")

        self.side = side
        self.timestamp = timestamp
        self.trade_id = trade_id

    @staticmethod
    def parse_from_msg(msg):
        symbol = msg["symbol"]
        price = float(msg["price"])
        quantity = float(msg["qty"])
        side = msg["side"]
        timestamp = msg["timestamp"]
        trade_id = msg.get("trade_id")

        return Trade(symbol, price, quantity, side, timestamp, trade_id)
