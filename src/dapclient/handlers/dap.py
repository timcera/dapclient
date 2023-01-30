"""A handler for remote datasets.

DAP handlers convert from different data formats (NetCDF, eg) to the internal
dapclient model. The dapclient client is just a handler that converts from a remote
dataset to the internal model.

"""

import codecs
import copy
import gzip
import io

# handlers should be set by the application
# http://docs.python.org/2/howto/logging.html#configuring-logging-for-a-library
import logging
import pickle
import pprint
import re
import sys
import urllib.parse
from io import BytesIO
from itertools import chain

import numpy

import dapclient.handlers.lib
import dapclient.model
import dapclient.net
import dapclient.parsers
from dapclient.lib import (
    DAP2_ARRAY_LENGTH_NUMPY_TYPE,
    DEFAULT_TIMEOUT,
    START_OF_SEQUENCE,
    BytesReader,
    StreamReader,
    combine_slices,
    encode,
    fix_slice,
    hyperslab,
    walk,
)
from dapclient.parsers.das import add_attributes, parse_das
from dapclient.parsers.dds import dds_to_dataset
from dapclient.parsers.dmr import dmr_to_dataset
from dapclient.responses.dods import DAP2_response_dtypemap

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

BLOCKSIZE = 512


class DAPHandler(dapclient.handlers.lib.BaseHandler):
    """Build a dataset from a DAP base URL."""

    def __init__(
        self,
        url,
        application=None,
        session=None,
        output_grid=True,
        timeout=DEFAULT_TIMEOUT,
        verify=True,
        user_charset="ascii",
        protocol=None,
    ):

        self.application = application
        self.session = session
        self.output_grid = output_grid
        self.timeout = timeout
        self.verify = verify
        self.user_charset = user_charset
        self.url = url

        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(self.url)
        self.scheme = scheme
        self.netloc = netloc
        self.path = path
        self.query = query
        self.fragment = fragment

        self.protocol = self.determine_protocol(protocol)

        self.projection, self.selection = dapclient.parsers.parse_ce(self.query)
        arg = (
            self.scheme,
            self.netloc,
            self.path,
            "&".join(self.selection),
            self.fragment,
        )
        self.base_url = urllib.parse.urlunsplit(arg)
        self.make_dataset()
        self.add_proxies()

    def determine_protocol(self, protocol):
        if protocol == "dap4":
            self.scheme = "http"
            return protocol
        if protocol == "dap2":
            return protocol
        if self.scheme == "dap4":
            self.scheme = "http"
            return "dap4"

        extension = self.path.split(".")[-1]
        if extension in ("dmr", "dap"):
            return "dap4"
        if extension in ("dds", "dods"):
            return "dap2"
        return "dap2"

    def make_dataset(
        self,
    ):
        if self.protocol == "dap4":
            self.dataset_from_dap4()
        else:
            self.dataset_from_dap2()
        self.attach_das()

    def dataset_from_dap4(self):
        dmr_url = urllib.parse.urlunsplit(
            (self.scheme, self.netloc, self.path + ".dmr", self.query, self.fragment)
        )
        r = dapclient.net.GET(
            dmr_url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )
        dapclient.net.raise_for_status(r)
        dmr = safe_charset_text(r, self.user_charset)
        self.dataset = dmr_to_dataset(dmr)

    def dataset_from_dap2(self):
        dds_url = urllib.parse.urlunsplit(
            (self.scheme, self.netloc, self.path + ".dds", self.query, self.fragment)
        )
        r = dapclient.net.GET(
            dds_url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )
        dapclient.net.raise_for_status(r)
        dds = safe_charset_text(r, self.user_charset)
        self.dataset = dds_to_dataset(dds)

    def attach_das(self):
        # Also pull the DAS and add additional attributes
        das_url = urllib.parse.urlunsplit(
            (self.scheme, self.netloc, self.path + ".das", self.query, self.fragment)
        )
        r = dapclient.net.GET(
            das_url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )
        dapclient.net.raise_for_status(r)
        das = safe_charset_text(r, self.user_charset)
        add_attributes(self.dataset, parse_das(das))

    def add_proxies(self):
        if self.protocol == "dap4":
            self.add_dap4_proxies()
        else:
            self.add_dap2_proxies()

    def add_dap4_proxies(self):
        # remove any projection from the base_url, leaving selections
        for var in walk(self.dataset, dapclient.model.BaseType):
            var.data = BaseProxyDap4(
                self.base_url,
                var.name,
                var.dtype,
                var.shape,
                application=self.application,
                session=self.session,
                timeout=self.timeout,
            )
        for var in walk(self.dataset, dapclient.model.GridType):
            var.set_output_grid(self.output_grid)

    def add_dap2_proxies(self):
        # now add data proxies
        for var in walk(self.dataset, dapclient.model.BaseType):
            var.data = BaseProxyDap2(
                self.base_url,
                var.id,
                var.dtype,
                var.shape,
                application=self.application,
                session=self.session,
                timeout=self.timeout,
            )
        for var in walk(self.dataset, dapclient.model.SequenceType):
            template = copy.copy(var)
            var.data = SequenceProxy(
                self.base_url,
                template,
                application=self.application,
                session=self.session,
                timeout=self.timeout,
            )

        # apply projections
        for var in self.projection:
            target = self.dataset
            while var:
                token, index = var.pop(0)
                target = target[token]
                if isinstance(target, dapclient.model.BaseType):
                    target.data.slice = fix_slice(index, target.shape)
                elif isinstance(target, dapclient.model.GridType):
                    index = fix_slice(index, target.array.shape)
                    target.array.data.slice = index
                    for s, child in zip(index, target.maps):
                        target[child].data.slice = (s,)
                elif isinstance(target, dapclient.model.SequenceType):
                    target.data.slice = index

        # retrieve only main variable for grid types:
        for var in walk(self.dataset, dapclient.model.GridType):
            var.set_output_grid(self.output_grid)


def get_charset(r, user_charset):
    charset = r.charset
    if not charset:
        charset = user_charset
    return charset


def safe_charset_text(r, user_charset):
    if r.content_encoding == "gzip":
        return (
            gzip.GzipFile(fileobj=BytesIO(r.body))
            .read()
            .decode(get_charset(r, user_charset))
        )
    r.charset = get_charset(r, user_charset)
    return r.text


def safe_dds_and_data(r, user_charset):
    if r.content_encoding == "gzip":
        raw = gzip.GzipFile(fileobj=BytesIO(r.body)).read()
    else:
        raw = r.body
    dds, data = raw.split(b"\nData:\n", 1)
    return dds.decode(get_charset(r, user_charset)), data


def safe_dmr_and_data(r, user_charset):
    if r.content_encoding == "gzip":
        raw = gzip.GzipFile(fileobj=BytesIO(r.body)).read()
    else:
        raw = r.body
    logger.info("Saving and splitting dmr+")
    try:
        dmr, data = raw.split(b"</Dataset>", 1)
    except ValueError:
        logger.exception(f"Failed to split the following DMR+ \n {raw}")

        picked_response = str(codecs.encode(pickle.dumps(r), "base64").decode())
        logger.exception(
            "pickled response (base64): \n ----BEGIN PICKLE----- \n %s -----END PICKLE-----"
            % picked_response
        )

    dmr = dmr[4:] + b"</Dataset>"
    dmr = dmr.decode(get_charset(r, user_charset))
    data = data[3:]
    return dmr, data


class BaseProxyDap2:
    """A proxy for remote base types.

    This class behaves like a Numpy array, proxying the data from a base type
    on a remote dataset.
    """

    def __init__(
        self,
        baseurl,
        id,
        dtype,
        shape,
        slice_=None,
        application=None,
        session=None,
        timeout=DEFAULT_TIMEOUT,
        verify=True,
        user_charset="ascii",
    ):
        self.baseurl = baseurl
        self.id = id
        self.dtype = dtype
        self.shape = shape
        self.slice = slice_ or tuple(slice(None) for s in self.shape)
        self.application = application
        self.session = session
        self.timeout = timeout
        self.verify = verify
        self.user_charset = user_charset

    def __repr__(self):
        return "BaseProxy(%s)" % ", ".join(
            map(repr, [self.baseurl, self.id, self.dtype, self.shape, self.slice])
        )

    def __getitem__(self, index):
        # build download url

        index = combine_slices(self.slice, fix_slice(index, self.shape))
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(self.baseurl)
        url = urllib.parse.urlunsplit(
            (
                scheme,
                netloc,
                path + ".dods",
                urllib.parse.quote(self.id) + hyperslab(index) + "&" + query,
                fragment,
            )
        ).rstrip("&")

        # download and unpack data
        logger.info(f"Fetching URL: {url}")
        r = dapclient.net.GET(
            url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )

        dapclient.net.raise_for_status(r)
        dds, data = safe_dds_and_data(r, self.user_charset)

        # Parse received dataset:
        dataset = dds_to_dataset(dds)
        dataset.data = unpack_dap2_data(BytesReader(data), dataset)
        return dataset[self.id].data

    def __len__(self):
        return self.shape[0]

    def __iter__(self):
        return iter(self[:])

    # Comparisons return a boolean array
    def __eq__(self, other):
        return self[:] == other

    def __ne__(self, other):
        return self[:] != other

    def __ge__(self, other):
        return self[:] >= other

    def __le__(self, other):
        return self[:] <= other

    def __gt__(self, other):
        return self[:] > other

    def __lt__(self, other):
        return self[:] < other


class BaseProxyDap4(BaseProxyDap2):
    def __init__(
        self,
        baseurl,
        id,
        dtype,
        shape,
        slice_=None,
        application=None,
        session=None,
        timeout=DEFAULT_TIMEOUT,
        verify=True,
        user_charset="ascii",
    ):
        self.baseurl = baseurl
        self.id = id
        self.dtype = dtype
        self.shape = shape
        self.slice = slice_ or tuple(slice(None) for s in self.shape)
        self.application = application
        self.session = session
        self.timeout = timeout
        self.verify = verify
        self.user_charset = user_charset

    def __repr__(self):
        return "Dap4BaseProxy(%s)" % ", ".join(
            map(repr, [self.baseurl, self.id, self.dtype, self.shape, self.slice])
        )

    def __getitem__(self, index):
        # build download url
        index = combine_slices(self.slice, fix_slice(index, self.shape))
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(self.baseurl)
        ce = "dap4.ce=" + urllib.parse.quote(self.id) + hyperslab(index) + query
        url = urllib.parse.urlunsplit(
            (scheme, netloc, path + ".dap", ce, fragment)
        ).rstrip("&")

        # download and unpack data
        logger.info(f"Fetching URL: {url}")

        r = dapclient.net.GET(
            url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )

        dapclient.net.raise_for_status(r)
        dmr, data = safe_dmr_and_data(r, self.user_charset)

        # Parse received dataset:
        dataset = dmr_to_dataset(dmr)
        dataset = unpack_dap4_data(BytesReader(data), dataset)

        self.checksum = dataset[self.id].attributes["checksum"]
        self.data = dataset[self.id].data
        return self.data


class SequenceProxy:
    """A proxy for remote sequences.

    This class behaves like a Numpy structured array, proxying the data from a
    sequence on a remote dataset. The data is streamed from the dataset,
    meaning it can be treated one record at a time before the whole data is
    downloaded.

    """

    shape = ()

    def __init__(
        self,
        baseurl,
        template,
        selection=None,
        slice_=None,
        application=None,
        session=None,
        timeout=DEFAULT_TIMEOUT,
        verify=True,
    ):
        self.baseurl = baseurl
        self.template = template
        self.selection = selection or []
        self.slice = slice_ or (slice(None),)
        self.application = application
        self.session = session
        self.timeout = timeout
        self.verify = verify

        # this variable is true when only a subset of the children are selected
        self.sub_children = False

    @property
    def dtype(self):
        return self.template.dtype

    def __repr__(self):
        return "SequenceProxy(%s)" % ", ".join(
            map(repr, [self.baseurl, self.template, self.selection, self.slice])
        )

    def __copy__(self):
        """Return a lightweight copy of the object."""
        return self.__class__(
            self.baseurl,
            self.template,
            self.selection[:],
            self.slice[:],
            self.application,
        )

    def __getitem__(self, key):
        """Return a new object representing a subset of the data."""
        out = copy.copy(self)

        # return the data for a children
        if isinstance(key, str):
            out.template = out.template[key]

        # return a new object with requested columns
        elif isinstance(key, list):
            out.sub_children = True
            out.template._visible_keys = key

        # return a copy with the added constraints
        elif isinstance(key, dapclient.handlers.lib.ConstraintExpression):
            out.selection.extend(str(key).split("&"))

        # slice data
        else:
            if isinstance(key, int):
                key = slice(key, key + 1)
            out.slice = combine_slices(self.slice, (key,))

        return out

    @property
    def url(self):
        """Return url from where data is fetched."""
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(self.baseurl)
        url = urllib.parse.urlunsplit(
            (
                scheme,
                netloc,
                path + ".dods",
                self.id + hyperslab(self.slice) + "&" + "&".join(self.selection),
                fragment,
            )
        ).rstrip("&")

        return url

    @property
    def id(self):
        """Return the id of this sequence."""
        if self.sub_children:
            id_ = ",".join(
                urllib.parse.quote(child.id) for child in self.template.children()
            )
        else:
            id_ = urllib.parse.quote(self.template.id)
        return id_

    def __iter__(self):
        # download and unpack data
        r = dapclient.net.GET(
            self.url,
            self.application,
            self.session,
            timeout=self.timeout,
            verify=self.verify,
        )
        dapclient.net.raise_for_status(r)

        i = r.app_iter
        if not hasattr(i, "__next__"):
            i = iter(i)

        # Fast forward past the DDS header
        # the pattern could span chunk boundaries though so make sure to check
        pattern = b"Data:\n"
        last_chunk = find_pattern_in_string_iter(pattern, i)

        if last_chunk is None:
            raise ValueError(f"Could not find data segment in response from {self.url}")

        # Then construct a stream consisting of everything from
        # 'Data:\n' to the end of the chunk + the rest of the stream
        def stream_start():
            yield last_chunk

        stream = StreamReader(chain(stream_start(), i))

        return unpack_sequence(stream, self.template)

    def __eq__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(f"{self.id}={encode(other)}")

    def __ne__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(
            f"{self.id}!={encode(other)}"
        )

    def __ge__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(
            f"{self.id}>={encode(other)}"
        )

    def __le__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(
            f"{self.id}<={encode(other)}"
        )

    def __gt__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(f"{self.id}>{encode(other)}")

    def __lt__(self, other):
        return dapclient.handlers.lib.ConstraintExpression(f"{self.id}<{encode(other)}")


def unpack_sequence(stream, template):
    """Unpack data from a sequence, yielding records."""
    # is this a sequence or a base type?
    sequence = isinstance(template, dapclient.model.SequenceType)

    # if there are no children, we use the template as the only column
    cols = list(template.children()) or [template]

    # if there are no strings and no nested sequences we can unpack record by
    # record easily
    simple = all(
        isinstance(c, dapclient.model.BaseType) and c.dtype.char not in "SU"
        for c in cols
    )

    if simple:
        dtype = numpy.dtype([("", c.dtype, c.shape) for c in cols])
        marker = stream.read(4)
        while marker == START_OF_SEQUENCE:
            rec = numpy.frombuffer(stream.read(dtype.itemsize), dtype=dtype)[0]
            if not sequence:
                rec = rec[0]
            yield rec
            marker = stream.read(4)
    else:
        marker = stream.read(4)
        while marker == START_OF_SEQUENCE:
            rec = unpack_children(stream, template)
            if not sequence:
                rec = rec[0]
            else:
                rec = tuple(rec)
            yield rec
            marker = stream.read(4)


def unpack_children(stream, template):
    """Unpack children from a structure, returning their data."""
    cols = list(template.children()) or [template]

    out = []
    for col in cols:
        # sequences and other structures
        if isinstance(col, dapclient.model.SequenceType):
            out.append(
                dapclient.handlers.lib.IterData(list(unpack_sequence(stream, col)), col)
            )
        elif isinstance(col, dapclient.model.StructureType):
            out.append(tuple(unpack_children(stream, col)))

        # unpack arrays
        else:
            out.extend(convert_stream_to_list(stream, col.dtype, col.shape, col.id))
    return out


def convert_stream_to_list(stream, parser_dtype, shape, id):
    out = []
    response_dtype = DAP2_response_dtypemap(parser_dtype)
    print(f"{shape=}")
    if shape:
        n = numpy.frombuffer(stream.read(4), DAP2_ARRAY_LENGTH_NUMPY_TYPE)[0]
        count = response_dtype.itemsize * n
        if response_dtype.char in "S":
            # Consider on 'S' and not 'SU' because
            # response_dtype.char should never be
            data = []
            for _ in range(n):
                k = numpy.frombuffer(stream.read(4), DAP2_ARRAY_LENGTH_NUMPY_TYPE)[0]
                data.append(stream.read(k))
                stream.read(-k % 4)
            out.append(
                numpy.array([str(x.decode("ascii")) for x in data], "S").reshape(shape)
            )
        else:
            stream.read(4)  # read additional length
            try:
                out.append(
                    numpy.frombuffer(stream.read(count), response_dtype)
                    .astype(parser_dtype)
                    .reshape(shape)
                )
            except ValueError as exc:
                if str(exc) == "total size of new array must be unchanged":
                    # server-side failure.
                    # it is expected that the user should be mindful of this:
                    raise RuntimeError(
                        """
                            Variable {urllib.parse.quote(id)} could not be
                            properly retrieved. To avoid this error consider
                            using open_url(..., output_grid=False).
                            """
                    ) from exc
                raise
            if response_dtype.char == "B":
                # Unsigned Byte type is packed to multiples of 4 bytes:
                stream.read(-n % 4)

    # special types: strings and bytes
    elif response_dtype.char in "S":
        # Consider on 'S' and not 'SU' because
        # response_dtype.char should never be
        # 'U'
        k = numpy.frombuffer(stream.read(4), DAP2_ARRAY_LENGTH_NUMPY_TYPE)[0]
        out.append(str(stream.read(k).decode("ascii")))
        stream.read(-k % 4)
    # usual data
    else:
        out.append(
            numpy.frombuffer(
                stream.read(response_dtype.itemsize), response_dtype
            ).astype(parser_dtype)[0]
        )
        if response_dtype.char == "B":
            # Unsigned Byte type is packed to multiples of 4 bytes:
            stream.read(3)
    return out


def unpack_dap2_data(xdr_stream, dataset):
    """Unpack a string of encoded data, returning data as lists."""
    return unpack_children(xdr_stream, dataset)


def decode_chunktype(chunk_type):
    encoding = f"{chunk_type:03b}"
    if sys.byteorder == "little":
        # If our machine's byteorder is little, we need to swap since the chunk_type is always big endian
        encoding = encoding[::-1]
    last_chunk = bool(int(encoding[0]))
    error = bool(int(encoding[1]))
    endian = {"0": ">", "1": "<"}[encoding[2]]
    return last_chunk, error, endian


def get_count(variable):
    count = int(numpy.array(variable.shape).prod())
    item_size = numpy.dtype(variable.dtype).itemsize
    count = count * item_size
    return count


def decode_variable(buffer, start, stop, variable, endian):
    dtype = variable.dtype
    dtype = dtype.newbyteorder(endian)
    data = numpy.frombuffer(buffer[start:stop], dtype=dtype).astype(dtype)
    data = data.reshape(variable.shape)
    return data


def stream2bytearray(xdr_stream):
    last = False
    buffer = bytearray()
    while not last:
        chunk = numpy.frombuffer(xdr_stream.read(4), dtype=">u4")
        chunk_size = (chunk & 0x00FFFFFF)[0]
        chunk_type = ((chunk >> 24) & 0xFF)[0]
        last, error, endian = decode_chunktype(chunk_type)
        buffer.extend(xdr_stream.read(chunk_size))
    return buffer


def get_endianness(xdr_stream):
    chunk_header = xdr_stream.peek(4)[0:4]
    chunk_header = numpy.frombuffer(chunk_header, dtype=">u4")[0]
    chunk_type = (chunk_header >> 24) & 0xFF
    last, error, endian = decode_chunktype(chunk_type)
    return endian


def unpack_dap4_data(xdr_stream, dataset):
    endian = get_endianness(xdr_stream)
    checksum_dtype = numpy.dtype(endian + "u4")
    buffer = stream2bytearray(xdr_stream)

    start = 0
    for variable_name in dataset:
        variable = dataset[variable_name]
        count = get_count(variable)
        stop = start + count
        data = decode_variable(
            buffer, start=start, stop=stop, variable=variable, endian=endian
        )
        checksum = numpy.frombuffer(
            buffer[stop : stop + 4], dtype=checksum_dtype
        ).byteswap("=")
        if isinstance(variable, dapclient.model.BaseType):
            variable._set_data(data)
        elif isinstance(variable, dapclient.model.GridType):
            variable._set_data([data.data])
        variable.attributes["checksum"] = checksum
        # Jump over the 4 byte chunk_header
        start = stop + 4
    return dataset


def find_pattern_in_string_iter(pattern, i):
    last_chunk = b""
    length = len(pattern)
    for this_chunk in i:
        last_chunk += this_chunk
        m = re.search(pattern, last_chunk)
        if m:
            return last_chunk[m.end() :]
        last_chunk = last_chunk[-length:]


def dump():  # pragma: no cover
    """Unpack dods response into lists.

    Return pretty-printed data.

    """
    dods = sys.stdin.read()
    dds, xdrdata = dods.split(b"\nData:\n", 1)
    dataset = dds_to_dataset(dds)
    xdr_stream = io.BytesIO(xdrdata)
    data = unpack_dap2_data(xdr_stream, dataset)
    pprint.pprint(data)
