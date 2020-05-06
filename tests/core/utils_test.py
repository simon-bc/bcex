from datetime import datetime, timedelta, timezone

import pytest
import pytz

from bcex.core.utils import (
    update_max_list,
    valid_datetime,
    datetime2unixepoch,
    unixepoch2datetime,
)


class TestUtils(object):
    @pytest.mark.parametrize(
        "dt_str, exp_dt",
        [
            (
                "2019-04-12T10:53:58+00:00",
                datetime(2019, 4, 12, 10, 53, 58, tzinfo=timezone(timedelta())),
            ),
            (
                "2019-03-12T02:53:51+01:00",
                datetime(2019, 3, 12, 2, 53, 51, tzinfo=timezone(timedelta(hours=1))),
            ),
        ],
    )
    def test_valid_datetime(self, dt_str, exp_dt):
        act_dt = valid_datetime(dt_str)
        assert act_dt == exp_dt

    @pytest.mark.parametrize(
        "l, e, n, exp",
        [
            ([], 12, 3, [12]),  # empty list no need to trim
            (["a", "bb"], "ccc", 2, ["bb", "ccc"]),  # need to update and trim
            (
                ["a", "bb", "ccc"],
                "d",
                2,
                ["ccc", "d"],
            ),  # need to update and trim initial too long
            (
                ["a", "bb", "ccc", 1],
                "d",
                4,
                ["bb", "ccc", 1, "d"],
            ),  # need to update and trim
        ],
    )
    def test_update_max_list(self, l, e, n, exp):
        act = update_max_list(l, e, n)
        assert exp == act

    def test_datetime2unixepoch(self):
        t1 = datetime(2015, 3, 15, 12, 15, 16)
        assert datetime2unixepoch(t1) == 1426421716000

        t2 = datetime(2015, 3, 15, 12, 15, 16, microsecond=5000, tzinfo=pytz.UTC)
        assert datetime2unixepoch(t2) == 1426421716005

        t3 = pytz.timezone("CET").localize(datetime(2015, 1, 15, 13, 15, 16, 150345))
        assert datetime2unixepoch(t3) == 1421324116150

    def test_unixepoch2datetime(self):
        t1 = datetime(2015, 3, 15, 12, 15, 16)
        assert unixepoch2datetime(datetime2unixepoch(t1))
        assert unixepoch2datetime(datetime2unixepoch(t1))

        t2 = datetime(2015, 3, 15, 12, 15, 16, tzinfo=pytz.UTC)
        assert unixepoch2datetime(datetime2unixepoch(t2))
        assert unixepoch2datetime(datetime2unixepoch(t2))

        t3 = datetime(2015, 6, 15, 13, 15, 16, tzinfo=pytz.timezone("CET"))
        assert unixepoch2datetime(datetime2unixepoch(t3))
        assert unixepoch2datetime(datetime2unixepoch(t3))
