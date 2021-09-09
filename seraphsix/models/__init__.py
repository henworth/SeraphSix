# pylama:ignore=W0401,W0611
import msgpack

from datetime import datetime

from seraphsix import constants
from seraphsix.models.destiny import *


def encode_data(obj):
    if isinstance(obj, datetime):
        obj = {
            "__datetime__": True,
            "as_str": obj.strftime(constants.DESTINY_DATE_FORMAT),
        }
    else:
        try:
            data = obj.to_dict()
        except AttributeError:
            pass
        else:
            obj = {"__destiny_dataclass__": type(obj).__name__, "as_str": data}
    return obj


def decode_data(obj):
    if "__datetime__" in obj:
        obj = datetime.strptime(obj["as_str"], constants.DESTINY_DATE_FORMAT)
    elif "__destiny_dataclass__" in obj:
        obj = eval(obj["__destiny_dataclass__"]).from_dict(obj["as_str"])
    return obj


def serializer(obj):
    return msgpack.packb(obj, default=encode_data)


def deserializer(obj):
    return msgpack.unpackb(obj, object_hook=decode_data)
