import builtins
from typing import Literal

import rich

from tele_acp.types import Format


def print(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    flush: Literal[False] = False,
    fmt: Format = Format.text,
) -> None:
    match fmt:
        case Format.json:
            builtins.print(*values, sep=sep, end=end, flush=flush)
        case _:
            rich.print(*values, sep=sep, end=end, flush=flush)


def get_str_len_for_int(n: int) -> int:
    import math

    if n > 0:
        return int(math.log10(n)) + 1
    elif n == 0:
        return 1
    else:
        return int(math.log10(-n)) + 2
