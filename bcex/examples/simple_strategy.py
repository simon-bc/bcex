import logging
from datetime import datetime

import pandas as pd
import pytz
from bcex.core.orders import OrderSide, OrderType
from bcex.core.websocket_client import Environment
from bcex.examples.trader import BaseTrader
from requests import get


def datetime2unixepoch(dt):
    """ Utility to transform a datetime instance into an unix epoch represented as an int.

    Parameters
    ----------
    dt: datetime

    Returns
    -------
    int
        unix epoch
    """
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)

    epoch = pytz.UTC.localize(datetime.utcfromtimestamp(0))
    delta = dt - epoch

    result = delta.total_seconds()
    result *= 1000

    return int(result)


def unixepoch2datetime(unixepoch):
    """Given a timestamp, it returns a datetime object.

    Parameters
    ----------
    unixepoch : int
       Timestamp. It can have either a second or millisecond precision

    Returns
    -------
    time : datetime
       Datetime object corresponding to the original timestamp
    """
    unixepoch = float(unixepoch) / 1000.0

    time = pytz.UTC.localize(datetime.utcfromtimestamp(unixepoch))

    return time


class SimpleStrategy(BaseTrader):
    def __init__(
        self,
        symbol,
        start_date,
        rolling_window=30,
        balance_percentage=0.1,
        granularity=3600,
        refresh_rate=60,
        env=Environment.STAGING,
        **kwargs,
    ):
        channel_kwargs = {"prices": {"granularity": granularity}}
        super().__init__(
            symbol,
            refresh_rate=refresh_rate,
            env=env,
            channels_kwargs=channel_kwargs,
            **kwargs,
        )
        self.rolling_window = rolling_window
        self.granularity = granularity
        self._historical_candles = None
        self.start_date = start_date
        self.balance_percentage = balance_percentage
        self.latest_timestamp = None

    def get_historical_candles(self):
        end_date = datetime.now(pytz.UTC)
        prices_url = (
            f"https://api.blockchain.com/nabu-gateway/markets/exchange/"
            f"prices?symbol={self.symbol}&start={datetime2unixepoch(self.start_date)}&end={datetime2unixepoch(end_date)}"
            f"&granularity={self.granularity}"
        )
        r = get(prices_url)
        res = r.json()
        df_res = pd.DataFrame(
            {
                unixepoch2datetime(rec[0]): {
                    "open": rec[1],
                    "high": rec[2],
                    "low": rec[3],
                    "close": rec[4],
                }
                for rec in res["prices"]
            }
        ).T
        return df_res

    @property
    def historical_candles(self):
        if self._historical_candles is None:
            self._historical_candles = self.get_historical_candles()
        return self._historical_candles

    def get_latest_candles(self):
        res = self.exchange.get_candles(self.symbol)
        if res:
            df_res = pd.DataFrame(
                {
                    unixepoch2datetime(rec[0]): {
                        "open": rec[1],
                        "high": rec[2],
                        "low": rec[3],
                        "close": rec[4],
                    }
                    for rec in res["prices"]
                }
            ).T
            return df_res
        return pd.DataFrame()

    @property
    def live_candles(self):
        return self.get_latest_candles()

    def get_candle_df(self):
        df = pd.concat([self.historical_candles, self.live_candles]).sort_index()
        return df

    def place_order_at_crossover(self, df):
        df["closing_prices_rolling_average"] = df.close.rolling(
            self.rolling_window
        ).mean()
        df["close_over_rolling_average"] = df.close > df.closing_prices_rolling_average
        last_row = df.iloc[-1]
        last_side_over = last_row.close_over_rolling_average
        moving_average = last_row.closing_prices_rolling_average
        self.latest_timestamp = last_row.index
        if last_side_over:
            # Was last over MA so if drops below then sell
            bid_price = self.exchange.get_bid_price(self.symbol)
            balance = self.exchange.get_available_balance(self.symbol.split("-")[0])
            logging.info(
                f"Moving Average {moving_average} current bid {bid_price}, placing sell limit order"
            )
            self.exchange.place_order(
                symbol=self.symbol,
                order_type=OrderType.LIMIT,
                quantity=balance * self.balance_percentage,
                price=moving_average,
                side=OrderSide.SELL,
                check_balance=True,
            )
        else:
            ask_price = self.exchange.get_ask_price(self.symbol)
            balance = self.exchange.get_available_balance(self.symbol.split("-")[1])
            logging.info(
                f"Moving Average {moving_average} current ask {ask_price}, placing buy limit order"
            )
            self.exchange.place_order(
                symbol=self.symbol,
                order_type=OrderType.LIMIT,
                quantity=(balance * self.balance_percentage) / moving_average,
                price=moving_average,
                side=OrderSide.BUY,
                check_balance=True,
            )

    def is_new_candle(self, candles):
        last_timestamp = candles.iloc[-1].index
        if last_timestamp > self.latest_timestamp:
            return True
        return False

    def handle_orders(self):
        candles = self.get_candle_df()
        if self.latest_timestamp is not None:
            if self.is_new_candle(candles):
                self.exchange.cancel_all_orders()
                self.place_order_at_crossover(candles)
        else:
            self.exchange.cancel_all_orders()
            self.place_order_at_crossover(candles)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
    )
    ss = SimpleStrategy("BTC-USD", start_date=datetime(2020, 4, 1))
    ss.run_loop()
