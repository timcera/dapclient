"""The DDS response.

The DDS response builds a representation of the structure of the dataset,
informing which variables are contained, their shape, type and dimensions.
Together with the DAS, the DDS describes all metadata associated with a given
dataset, allowing clients to introspect the variables and request data as
necessary.

"""

from functools import singledispatch
from importlib.metadata import version

from dapclient.lib import NUMPY_TO_DAP2_TYPEMAP
from dapclient.model import BaseType, DatasetType, GridType, SequenceType, StructureType
from dapclient.responses.lib import BaseResponse

INDENT = " " * 4


class DDSResponse(BaseResponse):
    """The DDS response."""

    __version__ = version("dapclient")

    def __init__(self, dataset):
        BaseResponse.__init__(self, dataset)
        self.headers.extend(
            [
                ("Content-description", "dods_dds"),
                ("Content-type", "text/plain; charset=ascii"),
            ]
        )

    def __iter__(self):
        for line in dds(self.dataset):
            yield line.encode("ascii")


@singledispatch
def dds(var, level=0, sequence=0):
    """Single dispatcher that generates the DDS response."""
    raise StopIteration


@dds.register(DatasetType)
def _(var, level=0, sequence=0):
    yield f"{level * INDENT}Dataset {{\n"
    for child in var.children():
        yield from dds(child, level + 1, sequence)
    yield f"{level * INDENT}}} {var.name};\n"


@dds.register(SequenceType)
def _sequencetype(var, level=0, sequence=0):
    yield f"{level * INDENT}Sequence {{\n"
    for child in var.children():
        yield from dds(child, level + 1, sequence + 1)
    yield f"{level * INDENT}}} {var.name};\n"


@dds.register(StructureType)
def _structuretype(var, level=0, sequence=0):
    yield f"{level * INDENT}Structure {{\n"
    for child in var.children():
        yield from dds(child, level + 1, sequence)
    yield f"{level * INDENT}}} {var.name};\n"


@dds.register(GridType)
def _gridtype(var, level=0, sequence=0):
    yield f"{level * INDENT}Grid {{\n"

    yield f"{(level + 1) * INDENT}Array:\n"
    yield from dds(var.array, level + 2, sequence)

    yield f"{(level + 1) * INDENT}Maps:\n"
    for map_ in var.maps.values():
        yield from dds(map_, level + 2, sequence)

    yield f"{level * INDENT}}} {var.name};\n"


@dds.register(BaseType)
def _basetype(var, level=0, sequence=0):
    shape = var.shape[sequence:]

    if var.dimensions:
        shape = "".join(map("[{0[0]} = {0[1]}]".format, zip(var.dimensions, shape)))
    elif len(shape) == 1:
        shape = f"[{var.name} = {shape[0]}]"
    else:
        shape = "".join(f"[{len}]" for len in shape)

    yield "{indent}{type} {name}{shape};\n".format(
        indent=level * INDENT,
        type=NUMPY_TO_DAP2_TYPEMAP[var.dtype.char],
        name=var.name,
        shape=shape,
    )
