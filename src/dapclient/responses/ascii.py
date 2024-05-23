"""The ASCII response.

The ASCII response is an unofficial response used to return the data as ASCII.
dapclient's implementation is reverse engineered from the official server.

"""

import copy
from functools import singledispatch
from importlib.metadata import version

import numpy as np

from dapclient.lib import encode
from dapclient.model import BaseType, SequenceType, StructureType
from dapclient.responses.dds import dds
from dapclient.responses.lib import BaseResponse


class ASCIIResponse(BaseResponse):
    """The ASCII response."""

    __version__ = version("dapclient")

    def __init__(self, dataset):
        BaseResponse.__init__(self, dataset)
        self.headers.extend(
            [
                ("Content-description", "dods_ascii"),
                ("Content-type", "text/plain; charset=ascii"),
            ]
        )

    def __iter__(self):
        for line in dds(self.dataset):
            yield line.encode("ascii")
        yield (45 * "-" + "\n").encode("ascii")

        for line in ascii(self.dataset):
            yield line.encode("ascii")


@singledispatch
def ascii(var, printname=True):
    """A single dispatcher for the ASCII response."""
    raise StopIteration


@ascii.register(SequenceType)
def _sequenctype(var, printname=True):
    yield ", ".join([child.id for child in var.children()])
    yield "\n"
    for rec in var.iterdata():
        out = copy.copy(var)
        out.__class__ = StructureType
        out.data = rec
        for i, line in enumerate(ascii(out, printname=False)):
            line = line.strip()
            if line and i > 0:
                yield ", "
            yield line
        yield "\n"


@ascii.register(StructureType)
def _structuretype(var, printname=True):
    for child in var.children():
        yield from ascii(child, printname)
        yield "\n"


@ascii.register(BaseType)
def _basetype(var, printname=True):
    if printname:
        yield var.id
        yield "\n"

    if not getattr(var, "shape", ()):
        yield encode(var.data)
    else:
        for indexes, value in zip(np.ndindex(var.shape), var.data.flat):
            yield "{indexes} {value}\n".format(
                indexes="[" + "][".join([str(idx) for idx in indexes]) + "]",
                value=encode(value),
            )
