class MessageType:
    ExecutionReport = "8"
    OrderCancelRejected = "9"


class ExecutionType:
    NEW = "0"
    CANCELLED = "4"
    EXPIRED = "C"
    REJECTED = "8"
    PARTIAL_FILL = "F"
    PENDING = "A"
    TRADE_BREAK = "H"
    ORDER_STATUS = "I"


class OrderStatus:
    PENDING = "pending"
    OPEN = "open"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FILLED = "filled"
    EXPIRED = "expired"

    @staticmethod
    def terminal_states():
        return [
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.FILLED,
            OrderStatus.EXPIRED,
        ]


class OrderResponse:
    def __init__(self, dict_response):
        self.message_type = dict_response.get("msgType")
        self.execution_type = dict_response.get("execType")
        self.execution_transaction_type = dict_response.get("execTransType")

        self.order_status = dict_response.get("ordStatus")
        self.order_type = dict_response.get("ordType")
        self.order_side = dict_response.get("side")

        self.sent_time = dict_response.get("sendingTime")
        self.transaction_time = dict_response.get("transactTime")

        self.client_order_id = dict_response.get("clOrdID")
        self.order_id = dict_response.get("orderID")
        self.execution_id = dict_response.get("execID")

        self.symbol = dict_response.get("symbol")

        self.price = dict_response.get("price")
        self.average_price = dict_response.get("avgPx")

        self.order_quantity = dict_response.get("orderQty")
        self.matched_quantity = dict_response.get("cumQty")
        self.left_quantity = dict_response.get("leavesQty")

    def to_str(self):
        msg_str = ""
        for attr in [
            "client_order_id",
            "order_id",
            "execution_id",
            "order_status",
            "symbol",
        ]:
            msg_str += f"{attr}: {getattr(self, attr)}, "

        return msg_str

    def to_dict(self):
        return {
            attr: getattr(self, attr)
            for attr in [
                "client_order_id",
                "order_id",
                "execution_id",
                "order_status",
                "price",
                "order_type",
                "order_side",
                "symbol",
                "order_quantity",
                "matched_quantity",
                "left_quantity",
            ]
        }
