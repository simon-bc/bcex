from datetime import datetime, timedelta, timezone

import pytest
from core.utils import update_max_list, valid_datetime


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
