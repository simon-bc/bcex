import iso8601 as iso8601


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
