import datetime as dt

from pydantic import BaseModel


class LastDayMetrics(BaseModel):
    date: dt.date
    total_amount_gained: float
