import uuid


class OrderSide:
    BUY = "buy"
    SELL = "sell"

    @staticmethod
    def is_valid(side_str):
        if side_str not in [OrderSide.SELL, OrderSide.BUY]:
            return False
        return True


class OrderType:
    MARKET = "market"
    LIMIT = "limit"
    STOP = "3"
    STOP_LIMIT = "4"
    CANCEL = "5"


class TimeInForce:
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTD = "GTD"


class OrderAction:
    CANCEL_ORDER = "CancelOrderRequest"
    PLACE_ORDER = "NewOrderSingle"
    BULK_CANCEL = "BulkCancelOrderRequest"


class Order:
    def __init__(
        self,
        order_type,
        symbol=None,
        time_in_force=None,
        side=None,
        order_quantity=None,
        price=None,
        expiry_date=None,
        stop_price=None,
        minimum_quantity=None,
        order_id=None,
        post_only=True,
    ):
        self.order_type = order_type
        self.symbol = symbol
        self.time_in_force = time_in_force
        self.side = side
        self.order_quantity = order_quantity
        self.price = price
        self.expiry_date = expiry_date
        self.stop_price = stop_price
        self.minimum_quantity = minimum_quantity
        self.client_order_id = str(uuid.uuid1())[:10] + "_bcexpy"

        self.order_id = order_id
        if self.order_type == OrderType.CANCEL:
            if self.order_id == -999:
                self.action = OrderAction.BULK_CANCEL
            else:
                self.action = OrderAction.CANCEL_ORDER
        else:
            self.action = OrderAction.PLACE_ORDER

        self.check_valid_order()
        self.post_only = post_only

    def __str__(self):
        return f"{self.order_id} - {self.side} {self.order_quantity}@{self.price} {self.symbol}"

    def check_valid_order(self):
        if self.action is OrderAction.PLACE_ORDER:
            if self.symbol is None:
                raise ValueError(
                    "Must have symbol for order type {}".format(self.order_type)
                )
            if self.side is None:
                raise ValueError(
                    "Must have side for order type {}".format(self.order_type)
                )
            if self.order_quantity is None:
                raise ValueError(
                    "Must have order_quantity for order type {}".format(self.order_type)
                )

        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if self.price is None:
                raise ValueError(
                    "Must have price for order type {}".format(self.order_type)
                )

            if self.time_in_force is None:
                raise ValueError(
                    "Must have time_in_force for order type {}".format(self.order_type)
                )

        if self.order_type in [OrderType.MARKET]:
            if self.price is not None:
                raise ValueError(
                    "Cannot have price for order type {}".format(self.order_type)
                )

            if self.time_in_force is not None:
                raise ValueError(
                    "Cannot have time_in_force for order type {}".format(
                        self.order_type
                    )
                )

        if self.time_in_force == TimeInForce.GTD:
            if self.expiry_date is None:
                raise ValueError(
                    "Must have expiry date for order type {}".format(self.order_type)
                )

        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if self.stop_price is None:
                raise ValueError(
                    "Must have stop price for order type {}".format(self.order_type)
                )

        if self.time_in_force == TimeInForce.IOC:
            if self.minimum_quantity is None:
                raise ValueError(
                    "Must have minimum quantity for order type {}".format(
                        self.order_type
                    )
                )

        if self.action == OrderAction.CANCEL_ORDER:
            if self.order_id is None:
                raise ValueError("Cancel Orders must have mercury id")

    def order_to_dict(self):
        if self.action == OrderAction.CANCEL_ORDER:
            res = {
                "action": "CancelOrderRequest",
                "channel": "trading",
                "orderID": self.order_id,
            }
        elif self.action == OrderAction.BULK_CANCEL:
            res = {
                "action": "BulkCancelOrderRequest",
                "channel": "trading",
                "orderID": -999,
            }
        elif self.action == OrderAction.PLACE_ORDER:
            res = {
                "action": "NewOrderSingle",
                "channel": "trading",
                "clOrdID": self.client_order_id,
                "symbol": self.symbol,
                "ordType": self.order_type,
                "timeInForce": self.time_in_force,
                "side": self.side,
                "orderQty": self.order_quantity,
            }
            if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
                res.update({"price": self.price})
                # TODO: restore this property
                # if self.post_only:
                #     res.update({"execInst": "ALO"})

            if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
                res.update({"stopPx": self.stop_price})
            if self.time_in_force == TimeInForce.IOC:
                res.update({"minQty": self.minimum_quantity})
            if self.time_in_force == TimeInForce.GTD:
                res.update({"expireDate": self.expiry_date})
        else:
            raise ValueError("Incorrect Action Type")
        return res
