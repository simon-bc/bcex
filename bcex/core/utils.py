from datetime import datetime

import iso8601 as iso8601
import pytz


def parse_balance(balances):
    return {
        b["currency"]: {"available": b["available"], "balance": b["balance"]}
        for b in balances
    }


def valid_datetime(s):
    """Parse a string to a valid datetime.

    Parameters
    ----------
    s : str
        The string representation of datetime.

    Return
    ------
    datetime
        Datetime parsed from the string.
    """

    return iso8601.parse_date(s)


def update_max_list(l, e, n):
    """Update a list and enforce maximum length"""
    l.append(e)
    return l[-n:]


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

    result = dt.timestamp()
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
