from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None  # type: ignore


def _now_eastern() -> datetime:
    tz = "US/Eastern"
    now = pd.Timestamp.now(tz)
    return now.to_pydatetime()


def get_last_trading_day(
    *,
    completed_session: bool = True,
    tz: str = "US/Eastern",
    now: Optional[datetime] = None,
) -> pd.Timestamp:
    """
    Return the last NYSE trading session date.

    If completed_session=True, and the current session has not yet reached the official
    close time (including early close), the previous session date is returned.

    Tries pandas_market_calendars (NYSE) if available; falls back to a weekday/holiday
    approximation using pandas USFederalHolidayCalendar.
    """
    now_ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz)

    # Try pandas_market_calendars for accurate schedule including early closes
    try:  # Accurate path
        import pandas_market_calendars as mcal  # type: ignore

        nyse = mcal.get_calendar("XNYS")
        # Look back a few weeks to be safe around long weekends
        start = (now_ts - pd.Timedelta(days=30)).normalize()
        end = now_ts.normalize() + pd.Timedelta(days=1)
        schedule = nyse.schedule(start_date=start, end_date=end)
        if schedule.empty:
            # Fallback to naive if something is off
            raise RuntimeError("Empty NYSE schedule")

        # Identify the most recent session row
        # If today is a trading day, it's the last row; else last row is a past day
        last_row = schedule.iloc[-1]
        last_session_date = schedule.index[-1]

        if completed_session:
            # If we're on the last session day and before market close (incl. early close),
            # use the previous session day
            if last_session_date.normalize() == now_ts.normalize():
                market_close = pd.Timestamp(last_row["market_close"]).tz_convert(tz)
                if now_ts < market_close:
                    # Use previous session
                    if len(schedule) >= 2:
                        prev_session_date = schedule.index[-2]
                        return pd.Timestamp(prev_session_date).tz_localize(None)
            # Otherwise use the last session
            return pd.Timestamp(last_session_date).tz_localize(None)
        else:
            # Not requiring completion: return the last scheduled trading day (today if applicable)
            return pd.Timestamp(last_session_date).tz_localize(None)

    except Exception:
        # Naive fallback: weekends + US Federal Holidays
        from pandas.tseries.holiday import USFederalHolidayCalendar  # type: ignore

        cal = USFederalHolidayCalendar()
        # Build a holiday list around the current date
        hol = cal.holidays(start=(now_ts - pd.Timedelta(days=365)), end=(now_ts + pd.Timedelta(days=30)))

        def is_trading_day(d: pd.Timestamp) -> bool:
            return (d.weekday() < 5) and (d.normalize() not in hol)

        d = now_ts.normalize()
        # If requiring completed session, step back if during current session
        # Assume NYSE close 16:00 ET for naive fallback
        if completed_session:
            market_close = d + pd.Timedelta(hours=16)
            if now_ts < market_close:
                d -= pd.Timedelta(days=1)
        # Walk back to the most recent trading day
        while not is_trading_day(d):
            d -= pd.Timedelta(days=1)
        return d.tz_localize(None)
