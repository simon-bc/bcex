import logging
from datetime import datetime, timedelta

import pandas as pd
import pytz
from bcex.core.orders import OrderSide, OrderType
from bcex.core.utils import datetime2unixepoch, unixepoch2datetime
from bcex.core.websocket_client import Environment, Channel
from bcex.examples.trader import BaseTrader
from requests import get


class CandlesStrategy(BaseTrader):
    """This is the base class for simple candle strategies, this looks waits for new candles and then calls the
    order_decision_from_candles method
    """

    CHANNELS = Channel.PRIVATE + [Channel.TICKER, Channel.SYMBOLS, Channel.PRICES]

    def __init__(
        self,
        symbol,
        start_date,
        heikin_ashi=False,
        granularity=3600,
        refresh_rate=60,
        env=Environment.PROD,
        **kwargs,
    ):

        """Initialise Strategy

        Parameters
        ----------
        symbol: Symbol
        start_date : datetime
        heikin_ashi : bool
            whether or not to use heikin ashi candles
        granularity : int
            the granularity for the candles in seconds can be supported granularity values are:
             60, 300, 900, 3600, 21600, 8640
        refresh_rate : int
            number of seconds before checking for new candle
        env : Environment
        kwargs : kwargs to pass to Interface
        """
        channel_kwargs = {"prices": {"granularity": granularity}}
        super().__init__(
            symbol,
            refresh_rate=refresh_rate,
            env=env,
            channels_kwargs=channel_kwargs,
            **kwargs,
        )
        self.heikin_ashi = heikin_ashi
        self.granularity = granularity
        self._historical_candles = None
        self.start_date = start_date
        self.latest_timestamp = None

    def get_historical_candles(self):
        """Gets historical candle data from rest api

        Returns
        -------
        df_res : pd.DataFrame
            dataframe of the historical candles
        """
        end_date = datetime.now(pytz.UTC)
        payload = {
            "symbol": self.symbol,
            "start": datetime2unixepoch(self.start_date),
            "end": datetime2unixepoch(end_date),
            "granularity": self.granularity,
        }
        prices_url = "https://api.blockchain.com/nabu-gateway/markets/exchange/prices?"
        r = get(prices_url, params=payload)
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
        return df_res.sort_index()

    @property
    def historical_candles(self):
        if self._historical_candles is None:
            self._historical_candles = self.get_historical_candles()
        return self._historical_candles

    def _check_candle_is_finished(self, rec):
        """Checks if a given candle is complet"""
        return unixepoch2datetime(rec[0]) + timedelta(
            seconds=self.granularity
        ) < datetime.now(pytz.UTC)

    def get_latest_candles(self):
        """Gets realtime candle data from websocket interface

        Returns
        -------
        df_res : pd.DataFrame
            dataframe of the realtime candles
        """
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
                    for rec in res
                    if self._check_candle_is_finished(rec)
                }
            ).T
            return df_res.sort_index()
        return pd.DataFrame()

    @property
    def live_candles(self):
        return self.get_latest_candles()

    def get_candle_df(self):
        """Gets df of all candle data

        Returns
        -------
        df : pd.DataFrame
            dataframe of candles
        """
        live_candles = self.live_candles
        if live_candles.empty:
            return self.historical_candles.copy()
        min_time = live_candles.iloc[0].name
        historical_candles = self.historical_candles[
            self.historical_candles.index < min_time
        ]
        df = pd.concat([historical_candles, live_candles]).sort_index()
        return df

    def is_new_candle(self, candles):
        """Checks if there is a new candle in the dataframe

        Parameters
        ----------
        candles : pd.DataFrame
            dataframe of candles

        Returns
        -------
        is_new_candle : bool
        """
        last_timestamp = candles.iloc[-1].name
        if last_timestamp > self.latest_timestamp:
            return True
        return False

    def make_candles_heikin_ashi(self, candles_df):
        """Converts candles to heikin_ashi candles

        Parameters
        ----------
        candles_df : pd.DataFrame
            dataframe of candles

        Returns
        -------
        candles_df : pd.DataFrame
            dataframe of heikin_ashi candles
        """
        candles_df["ha_close"] = (
            candles_df["open"]
            + candles_df["close"]
            + candles_df["high"]
            + candles_df["low"]
        ) / 4.0
        candles_df["ha_open"] = (
            (candles_df["open"] + candles_df["close"]) / 2.0
        ).shift(1)
        candles_df.loc[candles_df.ha_open.isna(), "ha_open"] = (
            candles_df["open"] + candles_df["close"]
        ) / 2
        candles_df["ha_high"] = candles_df[["high", "ha_close", "ha_open"]].max(axis=1)
        candles_df["ha_low"] = candles_df[["low", "ha_close", "ha_open"]].min(axis=1)
        candles_df.drop(["high", "low", "open", "close"], axis=1, inplace=True)
        candles_df.rename(
            {
                "ha_close": "close",
                "ha_open": "open",
                "ha_high": "high",
                "ha_low": "low",
            },
            axis=1,
            inplace=True,
        )
        return candles_df

    def act_on_new_candle(self, candles_df):
        """Calls order_decision_from_candles and sets latest timestamp

        Parameters
        ----------
        candles_df : pd.DataFrame
            dataframe of candles
        """
        if self.heikin_ashi:
            candles_df = self.make_candles_heikin_ashi(candles_df)
        self.order_decision_from_candles(candles_df)
        self.latest_timestamp = candles_df.iloc[-1].name

    def order_decision_from_candles(self, candles_df):
        raise NotImplementedError

    def handle_orders(self):
        """Method called by the base trader class, this checks if theres a new candle
        and calls the act_on_new_candle function if there is"""
        candles = self.get_candle_df()
        if self.latest_timestamp is not None:
            if self.is_new_candle(candles):
                logging.info("New Candle")
                self.act_on_new_candle(candles)
            else:
                logging.info("No New Candle")
        else:
            self.act_on_new_candle(candles)


class MovingAverageStrategy(CandlesStrategy):
    """Strategy that looks at the n window moving average, if the close of the last candle was above we set a sell
    order at the crossover point, and vise versa if it was below. This is to try to catch moment where the price moves
    through the moving average

    """

    CHANNELS = Channel.PRIVATE + [
        Channel.TICKER,
        Channel.SYMBOLS,
        Channel.PRICES,
        Channel.L2,
    ]

    def __init__(self, rolling_window=30, balance_fraction=0.1, **kwargs):
        """Initialise Strategy

        Parameters
        ----------
        rolling_window : int
            the number of candles to look back on when computing moving average
        balance_fraction : float
            the % of balance in given currency to place on order
        kwargs
        """
        super().__init__(**kwargs,)
        self.rolling_window = rolling_window
        self.balance_fraction = balance_fraction

    def order_decision_from_candles(self, df):
        """Looks at candles computes moving average and places trade

        Parameters
        ----------
        df : pd.DataFrame
            dataframe of candles
        """
        self.exchange.cancel_all_orders()
        df["closing_prices_rolling_average"] = df.close.rolling(
            self.rolling_window
        ).mean()
        df["close_over_rolling_average"] = df.close > df.closing_prices_rolling_average
        last_row = df.iloc[-1]
        last_side_over = last_row.close_over_rolling_average
        moving_average = last_row.closing_prices_rolling_average
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
                quantity=balance * self.balance_fraction,
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
                quantity=(balance * self.balance_fraction) / moving_average,
                price=moving_average,
                side=OrderSide.BUY,
                check_balance=True,
            )


class ReversalCandleStrategy(CandlesStrategy):
    """This Strategy looks for and trades on reversal candles, these are candles where the color changes after n of the
     other color. For example if there are 5 green candles then 1 red, we sell at the limit price which is the close
     of the prior candle"""

    def __init__(
        self,
        n_candles_before_reversal=3,
        ignore_none_candles=True,
        balance_fraction=0.1,
        **kwargs,
    ):
        """Initialise Strategy

        Parameters
        ----------
        n_candles_before_reversal : int
            number of candles of the opposite color before a change is classed as a reversal
        ignore_none_candles : bool
            How to treat candles where the price does not change
        balance_fraction : float
            the % of balance in given currency to place on order
        kwargs
        """
        super().__init__(**kwargs)
        self.n_candles_before_reversal = n_candles_before_reversal
        self.ignore_none_candles = ignore_none_candles
        self.balance_fraction = balance_fraction

    def is_reversal_candle(self, df):
        """Determines if the candle is a reversal candle

        Parameters
        ----------
        df : pd.DataFrame
            dataframe of candles

        Returns
        -------
        is_reversal_candle : bool
        """
        if df.candle_color.iloc[-1] is None:
            return False
        if self.ignore_none_candles:
            df = df[~df.candle_color.isna()]
        if df.candle_color.iloc[-1] == df.candle_color.iloc[-2]:
            return False

        prior_n_candles = df.iloc[(-1 - self.n_candles_before_reversal) : -1]
        if len(prior_n_candles.candle_color.unique()) == 1:
            return True
        return False

    def order_decision_from_candles(self, df):
        """Looks at candles computes candle color and if it is a reversal candle and places trade

        Parameters
        ----------
        df : pd.DataFrame
            dataframe of candles
        """
        self.exchange.cancel_all_orders()
        df.loc[df.close > df.open, "candle_color"] = "green"
        df.loc[df.close < df.open, "candle_color"] = "red"
        df.loc[df.close == df.open, "candle_color"] = None
        if self.is_reversal_candle(df):
            logging.info("REVERSAL CANDLE!!!!")
            if df.candle_color.iloc[-1] == "green":
                price = df.high.iloc[-1]
                balance = self.exchange.get_available_balance(self.symbol.split("-")[1])
                logging.info(
                    f"Green Candle after at least {self.n_candles_before_reversal} Red canndles, "
                    f"BUY at high of prior candle {price}"
                )
                self.exchange.place_order(
                    symbol=self.symbol,
                    order_type=OrderType.LIMIT,
                    quantity=(balance * self.balance_fraction) / price,
                    price=price,
                    side=OrderSide.BUY,
                    check_balance=True,
                )
            if df.candle_color.iloc[-1] == "red":
                price = df.low.iloc[-1]
                balance = self.exchange.get_available_balance(self.symbol.split("-")[0])
                logging.info(
                    f"Red Candle after at least {self.n_candles_before_reversal} green canndles, "
                    f"SELL at high of prior candle {price}"
                )
                self.exchange.place_order(
                    symbol=self.symbol,
                    order_type=OrderType.LIMIT,
                    quantity=balance * self.balance_fraction,
                    price=price,
                    side=OrderSide.SELL,
                    check_balance=True,
                )
        else:
            logging.info("Not a reversal candle waiting.....")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
    )
    ss = MovingAverageStrategy(
        symbol="BTC-USD",
        start_date=datetime(2020, 4, 1),
        granularity=300,
        refresh_rate=60,
    )
    ss.run_loop()
