"""Basic functions related to the DAP spec."""

import contextlib
import operator
from functools import reduce
from itertools import zip_longest
from sys import maxsize as MAXSIZE
from urllib.parse import quote as quote_

import numpy as np

from dapclient.exceptions import ConstraintExpressionError

START_OF_SEQUENCE = b"\x5a\x00\x00\x00"
END_OF_SEQUENCE = b"\xa5\x00\x00\x00"
STRING = "|S128"
DEFAULT_TIMEOUT = 120  # 120 seconds = 2 minutes

NUMPY_TO_DAP2_TYPEMAP = {
    "d": "Float64",
    "f": "Float32",
    "h": "Int16",
    "H": "UInt16",
    "i": "Int32",
    "l": "Int32",
    "q": "Int32",
    "I": "UInt32",
    "L": "UInt32",
    "Q": "UInt32",
    # DAP2 does not support signed bytes.
    # Its Byte type is unsigned and thus corresponds
    # to numpy's 'B'.
    # The consequence is that there is no natural way
    # in DAP2 to represent numpy's 'b' type.
    # Ideally, DAP2 would have a signed Byte type
    # and an unsigned UByte type and we would have the
    # following mapping: {'b': 'Byte', 'B': 'UByte'}
    # but this not how the protocol has been defined.
    # This means that numpy's 'b' must be mapped to Int16
    # and data must be upconverted in the DODS response.
    "b": "Int16",
    "B": "Byte",
    # There are no boolean types in DAP2. Upconvert to
    # Byte:
    "?": "Byte",
    "S": "String",
    # Map numpy's 'U' to String b/c
    # DAP2 does not explicitly support unicode.
    "U": "String",
}

# DAP2 demands big-endian 32 bytes signed integers
# www.opendap.org/pdf/dap_2_data_model.pdf
DAP2_ARRAY_LENGTH_NUMPY_TYPE = ">i"

DAP2_TO_NUMPY_RESPONSE_TYPEMAP = {
    "Float64": ">d",
    "Float32": ">f",
    # This is a weird aspect of the DAP2 specification.
    # For backward-compatibility, Int16 and UInt16 are
    # encoded as 32 bits integers in the response,
    # respectively:
    "Int16": ">i",
    "UInt16": ">I",
    "Int32": ">i",
    "UInt32": ">I",
    # DAP2 does not support signed bytes.
    # It's Byte type is unsigned and thus corresponds
    # to numpy 'B'.
    # The consequence is that there is no natural way
    # in DAP2 to represent numpy's 'b' type.
    # Ideally, DAP2 would have a signed Byte type
    # and a unsigned UByte type and we would have the
    # following mapping: {'Byte': 'b', 'UByte': 'B'}
    # but this not how the protocol has been defined.
    # This means that DAP2 Byte is unsigned and must be
    # mapped to numpy's 'B' type, usigned byte.
    "Byte": "B",
    # Map String to numpy's string type 'S' because
    # DAP2 does not explicitly support unicode.
    "String": "S",
    "URL": "S",
    #
    # These two types are not DAP2 but it is useful
    # to include them for compatibility with other
    # data sources:
    "Int": ">i",
    "UInt": ">I",
}

# Typemap from lower case DAP2 types to
# numpy dtype string with specified endiannes.
# Here, the endianness is very important:
LOWER_DAP2_TO_NUMPY_PARSER_TYPEMAP = {
    "float64": ">d",
    "float32": ">f",
    "int16": ">h",
    "uint16": ">H",
    "int32": ">i",
    "uint32": ">I",
    "int": ">i",
    "uint": ">I",
    # "int8": ">b",  # DAP2 does not support signed bytes
    "uint8": ">B",
    "byte": "B",
    "string": STRING,
    "url": STRING,
}

# Typemap from lower case DAP4 types to
# numpy dtype string with specified endianiness.
# Here, the endianness is very important:
DAP4_TO_NUMPY_PARSER_TYPEMAP = {
    "Float64": ">f8",
    "Float32": ">f4",
    "Float16": ">f2",
    "Int64": ">i8",
    "UInt64": ">u8",
    "Int32": ">i4",
    "UInt32": ">u4",
    "Int16": ">i2",
    "UInt16": ">u2",
    "Int8": ">i1",
    "UInt8": ">u1",
    "Byte": "B",
    "String": STRING,
    "Url": STRING,
}


def quote(name):
    """Return quoted name according to the DAP specification.

    Parameters
    ----------
    name : str
        Name to quote.

    Examples
    --------
    >>> quote("White space")
    'White%20space'
    >>> quote("Period.")
    'Period%2E'
    """
    safe = "%_!~*'-\"/"
    return quote_(name.encode("utf-8"), safe=safe).replace(".", "%2E")


def encode(obj):
    """Return an object encoded to its DAP representation.

    Parameters
    ----------
    obj : object
        Object to encode.
    """
    with contextlib.suppress(TypeError):
        if np.all(np.isnan(obj)):
            return "NaN"
    if isinstance(obj, np.ndarray) and obj.dtype.char in "SU":
        return f'"{obj}"'

    try:
        return f"{obj:.6g}"
    except (ValueError, TypeError):
        return f'"{obj}"'


def fix_slice(slice_, shape):
    """Return a normalized slice.

    This is based on this document:
    http://docs.scipy.org/doc/numpy/reference/arrays.indexing.html

    Parameters
    ----------
    slice_ : slice or tuple of slices
        Slice to normalize.
    shape : tuple of ints
        Shape of the array being sliced.

    Returns
    -------
    fix_slice : tuple of slices
        This function returns a slice so that it has the same length of
        `shape`, and no negative indexes, if possible.
    """
    # convert `slice_` to a tuple
    if not isinstance(slice_, tuple):
        slice_ = (slice_,)

    # expand Ellipsis and make `slice_` at least as long as `shape`
    expand = len(shape) - len(slice_)
    out = []
    for sli in slice_:
        if sli is Ellipsis:
            out.extend((slice(None),) * (expand + 1))
            expand = 0
        else:
            out.append(sli)
    slice_ = tuple(out) + (slice(None),) * expand

    out = []
    for slic, shp in zip(slice_, shape):
        if isinstance(slic, int):
            if slic < 0:
                slic += shp
            out.append(slic)
        else:
            k = slic.step or 1

            i = slic.start
            if i is None:
                i = 0
            elif i < 0:
                i += shp

            j = slic.stop
            if j is None or j > shp:
                j = shp
            elif j < 0:
                j += shp

            out.append(slice(i, j, k))

    return tuple(out)


def combine_slices(slice1, slice2):
    """Return two tuples of slices combined sequentially.

    These two should be equal:

    x[ combine_slices(s1, s2) ] == x[s1][s2]

    Parameters
    ----------
    slice1 : tuple of slices
        First slice.
    slice2 : tuple of slices
        Second slice.
    """
    out = []
    for exp1, exp2 in zip_longest(slice1, slice2, fillvalue=slice(None)):
        if isinstance(exp1, int):
            exp1 = slice(exp1, exp1 + 1)
        if isinstance(exp2, int):
            exp2 = slice(exp2, exp2 + 1)

        start = (exp1.start or 0) + (exp2.start or 0)
        step = (exp1.step or 1) * (exp2.step or 1)

        if exp1.stop is None and exp2.stop is None:
            stop = None
        elif exp1.stop is None:
            stop = (exp1.start or 0) + exp2.stop
        elif exp2.stop is None:
            stop = exp1.stop
        else:
            stop = min(exp1.stop, (exp1.start or 0) + exp2.stop)

        out.append(slice(start, stop, step))
    return tuple(out)


def hyperslab(slice_):
    """Return a DAP representation of a multidimensional slice.

    Parameters
    ----------
    slice_ : tuple of slices
        Slice to convert to DAP representation.
    """
    slice_ = list(slice_) if isinstance(slice_, tuple) else [slice_]
    while slice_ and slice_[-1] == slice(None):
        slice_.pop(-1)

    return "".join(
        f"[{s.start or 0}:{s.step or 1}:{(s.stop or MAXSIZE) - 1}]" for s in slice_
    )


def walk(var, ltype=object):
    """Yield all variables of a given type from a dataset.

    The iterator returns also the parent variable.

    Parameters
    ----------
    var : object
        Variable to start the walk from.
    ltype : type
        Type of the variables to yield.
    """
    if isinstance(var, ltype):
        yield var
    for child in var.children():
        yield from walk(child, ltype)


def fix_shorthand(projection, dataset):
    """Fix shorthand notation in the projection.

    Some clients request variables by their name, not by the id. This is called
    the "shorthand notation", and it has to be fixed. This function will return
    a new projection with no shorthand calls.

    Parameters
    ----------
    projection : list of lists of tuples
        Projection to fix.
    dataset : DatasetType
        Dataset to use to fix the shorthand notation.
    """
    out = []
    for var in projection:
        if len(var) == 1 and var[0][0] not in list(dataset.keys()):
            token, slice_ = var.pop(0)
            for child in walk(dataset):
                if token == child.name:
                    if var:
                        raise ConstraintExpressionError(
                            f"Ambiguous shorthand notation request: {token}"
                        )
                    var = [(parent, ()) for parent in child.id.split(".")[:-1]] + [
                        (token, slice_)
                    ]
        out.append(var)
    return out


def get_var(dataset, id_):
    """Given an id, return the corresponding variable from the dataset.

    Parameters
    ----------
    dataset : DatasetType
        Dataset to use to get the variable.
    id_ : str
        Id of the variable to get.
    """
    tokens = id_.split(".")
    return reduce(operator.getitem, [dataset] + tokens)


def decode_np_strings(numpy_var):
    """Given a fixed-width numpy string, decode it to a unicode type.

    Parameters
    ----------
    numpy_var : numpy.ndarray
        Numpy array to decode.
    """
    if isinstance(numpy_var, bytes) and hasattr(numpy_var, "tobytes"):
        return numpy_var.tobytes().decode("utf-8")
    return numpy_var


def load_from_entry_point_relative(rel, package):
    """Load a class from an entry point relative to a package.

    Parameters
    ----------
    rel : pkg_resources.EntryPoint
        Entry point to load.
    package : str
        Package to use as a reference.
    """
    try:
        loaded = getattr(
            __import__(
                rel.module_name.replace(f"{package}.", "", 1),
                globals(),
                None,
                [rel.attrs[0]],
                1,
            ),
            rel.attrs[0],
        )
        return rel.name, loaded
    except ImportError:
        # This is only used in handlers testing:
        return rel.name, rel.load()


class StreamReader:
    """Class to allow reading a `urllib3.HTTPResponse`."""

    def __init__(self, stream):
        self.stream = stream
        self.buf = bytearray()

    def read(self, num):
        """Read and return `num` bytes."""
        while len(self.buf) < num:
            bytes_read = next(self.stream)
            self.buf.extend(bytes_read)

        out = bytes(self.buf[:num])
        self.buf = self.buf[num:]
        return out


class BytesReader:
    """Class to allow reading a `bytes` object."""

    def __init__(self, data):
        self.data = data

    def read(self, num):
        """Read and return `num` bytes."""
        out = self.data[:num]
        self.data = self.data[num:]
        return out

    def peek(self, num):
        return self.data[:num]
