import random
import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal


# 亚洲/上海时区（UTC+8），替代 pytz.timezone("Asia/Shanghai")
_SHANGHAI_TZ = timezone(timedelta(hours=8))

# arrow 格式化占位符 → strftime 格式
_ARROW_FMT_MAP = [
    ("YYYY", "%Y"),
    ("MM", "%m"),
    ("DD", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
]


def _arrow_fmt_to_strftime(fmt: str) -> str:
    for arrow_token, strftime_token in _ARROW_FMT_MAP:
        fmt = fmt.replace(arrow_token, strftime_token)
    return fmt


class _ArrowLike:
    """用标准库 datetime 模拟 arrow.Arrow 的常用接口"""

    __slots__ = ("_dt",)

    def __init__(self, dt: datetime):
        self._dt = dt

    def format(self, fmt: str) -> str:
        return self._dt.strftime(_arrow_fmt_to_strftime(fmt))

    @property
    def int_timestamp(self) -> int:
        return int(self._dt.timestamp())

    def shift(self, **kwargs) -> "_ArrowLike":
        return _ArrowLike(self._dt + timedelta(**kwargs))


def arrow_now():
    return _ArrowLike(datetime.now(_SHANGHAI_TZ))


def arrow_get(time: str):
    """解析时间字符串，兼容 arrow.get 的常用格式"""
    if not isinstance(time, str):
        return _ArrowLike(time)
    # 尝试常见格式
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(time, fmt)
            return _ArrowLike(dt.replace(tzinfo=_SHANGHAI_TZ))
        except ValueError:
            continue
    # 兜底：ISO 格式
    try:
        dt = datetime.fromisoformat(time)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_SHANGHAI_TZ)
        return _ArrowLike(dt)
    except ValueError:
        raise ValueError(f"无法解析时间字符串: {time}")


def join(arr: list, sep: str = ""):
    # filter all empty value
    arr = list(filter(lambda x: x, arr))
    return sep.join(arr)


def fixed_two_decimal_digits(num: int, to_number: bool = False):
    result = "{:.2f}".format(num)
    if to_number:
        return float(result)
    return result


def create_match_func_factory(fuzzy: bool = False):
    def is_keyword_matched(keywords: list, text: str):
        for keyword in keywords:
            if fuzzy:
                if text.startswith(keyword):
                    return True
            else:
                if text == keyword:
                    return True
        return False

    return is_keyword_matched


def get_object_values(obj: dict):
    vs = obj.values()
    ret = []
    for v in vs:
        if isinstance(v, list):
            ret.extend(v)
        else:
            ret.append(v)
    return ret


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass


class ArrowUtil:
    @staticmethod
    def is_date_outed(time: str):
        return arrow_get(time).format("YYYY-MM-DD") != arrow_now().format("YYYY-MM-DD")

    @staticmethod
    def get_arrow_gap_timestamp(time_1: str, time_2: str):
        return arrow_get(time_1).int_timestamp - arrow_get(time_2).int_timestamp

    @classmethod
    def get_arrow_gap_minutes(cls, time_1: str, time_2: str):
        return cls.get_arrow_gap_timestamp(time_1, time_2) / 60

    @staticmethod
    def complete_date_with_today_from_h_s(text: str):
        """
        10:00 -> 2020-01-01 10:00:00
        """
        return f'{arrow_now().format("YYYY-MM-DD")} {text.strip()}:00'

    @staticmethod
    def is_now_in_time_range(start: str, end: str):
        """
        start/end: YYYY-MM-DD HH:mm:ss
        """
        start_timestamp = arrow_get(start).int_timestamp
        end_timestamp = arrow_get(end).int_timestamp
        now_timestamp = arrow_now().int_timestamp
        return start_timestamp <= now_timestamp <= end_timestamp

    @staticmethod
    def get_time_with_shift(time: str, shift_mins: int = 0, shift_days: int = 0):
        """
        start_time: YYYY-MM-DD HH:mm:ss
        duration: minutes
        """
        if shift_days:
            shift_mins += shift_days * 24 * 60
        return arrow_get(time).shift(minutes=shift_mins).format("YYYY-MM-DD HH:mm:ss")

    @staticmethod
    def lt(time_1: str, time_2: str):
        return arrow_get(time_1).int_timestamp < arrow_get(time_2).int_timestamp

    @staticmethod
    def get_now_time():
        return arrow_now().format("YYYY-MM-DD HH:mm:ss")

    @staticmethod
    def calc_diff_minutes(time_1: str, time_2: str):
        return int(
            (arrow_get(time_1).int_timestamp - arrow_get(time_2).int_timestamp) / 60
        )

    @staticmethod
    def date_improve(time: str):
        ins = arrow_get(time)
        is_today = ins.format("YYYY-MM-DD") == arrow_now().format("YYYY-MM-DD")
        if is_today:
            return ins.format("HH:mm")
        is_this_year = ins.format("YYYY") == arrow_now().format("YYYY")
        if is_this_year:
            return ins.format("MM-DD HH:mm")
        return ins.format("YYYY-MM-DD HH:mm")

    @staticmethod
    def get_time_diff_days(time_1: str, time_2: str):
        """
        time_1 - time_2
        """
        time_1 = arrow_get(time_1).format("YYYY-MM-DD")
        time_2 = arrow_get(time_2).format("YYYY-MM-DD")
        return int(
            (arrow_get(time_1).int_timestamp - arrow_get(time_2).int_timestamp)
            / (60 * 60 * 24)
        )


class Random:

    nums = []
    max_nums = 500

    @staticmethod
    def get_secure_random_number():
        cryptogen = random.SystemRandom()
        return cryptogen.random()

    @staticmethod
    def generate_secure_random_number():
        return secrets.randbits(256) / ((1 << 256) - 1)

    @classmethod
    def get_single_random(cls):
        # num_1 = cls.generate_secure_random_number()
        num_2 = cls.generate_secure_random_number()
        return num_2

    @classmethod
    def fill(cls):
        while len(cls.nums) < cls.max_nums:
            cls.nums.append(cls.get_single_random())

    @classmethod
    def random(cls):
        if len(cls.nums) == 0:
            cls.fill()
        return cls.nums.pop()

class NumberUtils():

    @classmethod
    def plus(cls, a: float, b: float):
        ret = Decimal(a) + Decimal(b)
        if cls.is_zero(ret):
            return 0
        return float(ret)
    
    @classmethod
    def minus(cls, a: float, b: float):
        ret = Decimal(a) - Decimal(b)
        if cls.is_zero(ret):
            return 0
        return float(ret)
    
    @staticmethod
    def is_zero(a: float):
        return Decimal(a).quantize(Decimal('0.000')) == 0
    