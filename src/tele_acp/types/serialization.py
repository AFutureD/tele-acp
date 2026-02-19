from enum import Enum


class Format(str, Enum):
    text = "text"
    json = "json"


class Order(str, Enum):
    asc = "asc"
    desc = "desc"
