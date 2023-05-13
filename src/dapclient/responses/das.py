"""The DAS response.

The DAS response describes the attributes associated with a dataset and its
variables. Together with the DDS the DAS response completely describes the
metadata of a dataset, allowing it to be introspected and data to be
downloaded.
"""

from collections.abc import Iterable
from functools import singledispatch

import numpy as np
from pkg_resources import get_distribution

from dapclient.lib import NUMPY_TO_DAP2_TYPEMAP, encode, quote
from dapclient.model import BaseType, DatasetType, GridType, SequenceType, StructureType
from dapclient.responses.lib import BaseResponse

INDENT = " " * 4


class DASResponse(BaseResponse):
    """The DAS response."""

    __version__ = get_distribution("dapclient").version

    def __init__(self, dataset):
        BaseResponse.__init__(self, dataset)
        self.headers.extend(
            [
                ("Content-description", "dods_das"),
                ("Content-type", "text/plain; charset=ascii"),
            ]
        )

    def __iter__(self):
        for line in das(self.dataset):
            try:
                yield line.encode("ascii")
            except UnicodeDecodeError:
                yield line.encode("UTF-8")


@singledispatch
def das(var, level=0):
    """Single dispatcher that generates the DAS response."""
    raise StopIteration


@das.register(DatasetType)
def _datasettype(var, level=0):
    yield f"{level * INDENT}Attributes {{\n"

    for attr in sorted(var.attributes.keys()):
        values = var.attributes[attr]
        yield from build_attributes(attr, values, level + 1)

    for child in var.children():
        yield from das(child, level=level + 1)
    yield f"{level * INDENT}}}\n"


@das.register(StructureType)
@das.register(SequenceType)
def _structuretype(var, level=0):
    yield f"{level * INDENT}{var.name} {{\n"

    for attr in sorted(var.attributes.keys()):
        values = var.attributes[attr]
        yield from build_attributes(attr, values, level + 1)

    for child in var.children():
        yield from das(child, level=level + 1)
    yield f"{level * INDENT}}}\n"


@das.register(BaseType)
@das.register(GridType)
def _basetypegridtype(var, level=0):
    yield f"{level * INDENT}{var.name} {{\n"

    for attr in sorted(var.attributes.keys()):
        values = var.attributes[attr]
        if np.asarray(values).size > 0:
            yield from build_attributes(attr, values, level + 1)
    yield f"{level * INDENT}}}\n"


def build_attributes(attr, values, level=0):
    """Recursive function to build the DAS.

    This function recursively builds the DAS response. It is used by the
    :func:`das` function to build the DAS response.

    Parameters
    ----------
    attr : str
        The name of the attribute.
    values : object
        The value of the attribute.
    level : int
        The indentation level.

    Yields
    ------
    build_attributes : str
        The DAS response.
    """
    # check for metadata
    if isinstance(values, dict):
        yield f"{level * INDENT}{attr} {{\n"
        for k, v in values.items():
            yield from build_attributes(k, v, level + 1)
        yield f"{level * INDENT}}}\n"
    else:
        # get type
        ltype = get_type(values)

        # encode values
        if (
            isinstance(values, str)
            or not isinstance(values, Iterable)
            or getattr(values, "shape", None) == ()
        ):
            values = [encode(values)]
        else:
            values = map(encode, values)

        yield f"{level * INDENT}{ltype} {quote(attr)} {', '.join(values)};\n"


def get_type(values):
    """Extract the type of a variable.

    This function tries to determine the DAP type of a Python variable using
    several methods.

    Parameters
    ----------
    values : object
        The Python object to determine the type of.

    Returns
    -------
    get_type : str
        Returns the DAP type as a string.
    """
    if hasattr(values, "dtype"):
        return NUMPY_TO_DAP2_TYPEMAP[values.dtype.char]
    if isinstance(values, str) or not isinstance(values, Iterable):
        return type_convert(values)
    # if there are several values, they may have different types, so we
    # need to convert all of them and use a precedence table
    types = [type_convert(val) for val in values]
    precedence = ["String", "Float64", "Int32"]
    types.sort(key=precedence.index)
    return types[0]


def type_convert(obj):
    """Map Python objects to the corresponding Opendap types.

    Parameters
    ----------
    obj : object
        The python object to convert.

    Returns
    -------
    type_convert : str
        Returns the DAP representation of the type as a string.
    """
    if isinstance(obj, float):
        return "Float64"
    if isinstance(obj, int):
        return "Int32"
    return "String"
