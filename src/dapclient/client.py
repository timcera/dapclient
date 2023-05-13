"""
dapclient client.

This module contains functions to access DAP servers. The most common use is to
open a dataset by its canonical URL, ie, without any DAP related extensions
like dds/das/dods/html. Here is an example:

    >>> from dapclient.client import open_url
    >>> dataset = open_url("http://test.dapclient.org/coads.nc")

This will return a `DatasetType` object, which is a container for lazy
evaluated objects. Data is downloaded automatically when arrays are sliced or
when sequences are iterated.

It is also possible to download data directly from a dods (binary) response.
This allows calling server-specific functions, like those supported by the
Ferret and the GrADS data servers:

    >>> from dapclient.client import open_dods_url
    >>> dataset = open_dods_url(
    ...     "http://test.pydap.org/coads.nc.dods",
    ...     metadata=True)

Setting the `metadata` flag will also request the das response, populating the
dataset with the corresponding metadata.

If the dods response has already been downloaded, it is possible to open it as
if it were a remote dataset. Optionally, it is also possible to specify a das
response:

    >>> from dapclient.client import open_file
    >>> dataset = open_file(
    ...     "/path/to/file.dods", "/path/to/file.das")  #doctest: +SKIP

Remote datasets opened with `open_url` can call server functions. dapclient has
a lazy mechanism for function call, supporting any function. Eg, to call the
`geogrid` function on the server:

    >>> dataset = open_url(
    ...     'http://test.opendap.org/dap/data/nc/coads_climatology.nc')
    >>> new_dataset = dataset.functions.geogrid(dataset.SST, 10, 20, -10, 60)
    >>> print(new_dataset.SST.SST.shape) #doctest: +SKIP
    (12, 12, 21)

"""

from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

import numpy as np

import dapclient.handlers.dap
import dapclient.lib
import dapclient.model
import dapclient.net
import dapclient.parsers.das
import dapclient.parsers.dds
import dapclient.parsers.dmr


def open_url(
    url,
    application=None,
    session=None,
    output_grid=True,
    timeout=dapclient.lib.DEFAULT_TIMEOUT,
    verify=True,
    user_charset="ascii",
    protocol=None,
):
    """Open a remote URL, returning a dataset.

    Parameters
    ----------
    url : str
        The URL of the dataset.
    application : str, optional
        The application to use when requesting the dataset.
    session : requests.Session, optional
        A requests session to use when requesting the dataset.
    output_grid : bool, optional
        Set output_grid to `False` to retrieve only main arrays and never
        retrieve coordinate axes.
    timeout : int, optional
        The timeout for the request.
    verify : bool, optional
        Verify SSL certificates.
    user_charset : str, optional
        The charset to use when decoding strings.
    protocol : str, optional
        The protocol to use when requesting the dataset.
    """
    handler = dapclient.handlers.dap.DAPHandler(
        url,
        application,
        session,
        output_grid,
        timeout=timeout,
        verify=verify,
        user_charset=user_charset,
        protocol=protocol,
    )
    dataset = handler.dataset

    # attach server-side functions
    dataset.functions = Functions(url, application, session, timeout=timeout)

    return dataset


def open_file(file_path, das_path=None):
    """Open a file depending on the file extension.

    Parameters
    ----------
    file_path : str
        The path to the file.
    das_path : str, optional
        The path to the das file.
    """
    extension = file_path.split(".")[-1]
    if extension == "dods":
        return open_dods_file(file_path=file_path, das_path=das_path)
    if extension == "dap":
        return open_dap_file(file_path=file_path)
    if extension == "dds":
        return None
    if extension == "dmr":
        return open_dmr_file(file_path=file_path)


def get_dmr_length(file_path):
    """Get the length of the DMR in a `.dap` (dap4) response.

    Parameters
    ----------
    file_path : str
        The path to the file.
    """
    with open(file_path, "rb") as f:
        # First two bytes are CRLF
        if f.peek()[0:2] == b"\x04\x00":
            f.seek(2)
            dmr_len = np.frombuffer(f.read(2), dtype=">u2")[0]
        else:
            dap = f.read()
            dmr = b"<?xml" + dap.split(b"<?xml")[1]
            dmr = dmr.split(b"</Dataset>")[0] + b"</Dataset>\n\r\n"
            dmr_len = len(dmr)
    return dmr_len


def open_dmr_file(file_path):
    """Open a .dmr file.

    Parameters
    ----------
    file_path : str
        The path to the file.
    """
    dmr_len = get_dmr_length(file_path)
    with open(file_path, "rb") as f:
        if f.peek()[0:2] == b"\x04\x00":
            # First 2 bytes are CRLF, second two bytes give the length of the
            # DMR; we skip over them
            f.seek(4)
            # We read the DMR minus the CRLF and newline (3 bytes)
        dmr = f.read(dmr_len)
    dmr = dmr.decode("ascii")
    dataset = dapclient.parsers.dmr.dmr_to_dataset(dmr)
    return dataset


def open_dap_file(file_path):
    """Open a file downloaded from a `.dap` (dap4) response.

    Parameters
    ----------
    file_path : str
        The path to the file.
    """
    dataset = open_dmr_file(file_path)

    with open(file_path, "rb") as f:
        dmr_len = get_dmr_length(file_path)
        f.seek(dmr_len)
        _ = f.read(4)  # toss first 4 bytes
        dapclient.handlers.dap.unpack_dap4_data(f, dataset)
    return dataset


def open_dods_file(file_path, das_path=None):
    """Open a file downloaded from a `.dods` (dap2) response, returning a dataset.

    Parameters
    ----------
    file_path : str
        The path to the file.
    das_path : str, optional
        The path to the das file.  The `.das` response is used to assign
        attributes to the dataset.
    """
    dds = ""
    # This file contains both ascii _and_ binary data
    # Let's handle them separately in sequence
    # Without ignoring errors, the IO library will
    # actually read past the ascii part of the
    # file (despite our break from iteration) and
    # will error out on the binary data
    with open(
        file_path, buffering=1, encoding="ascii", newline="\n", errors="ignore"
    ) as f:
        for line in f:
            if line.strip() == "Data:":
                break
            dds += line
    dataset = dapclient.parsers.dds.dds_to_dataset(dds)
    pos = len(dds) + len("Data:\n")

    with open(file_path, "rb") as f:
        f.seek(pos)
        dataset.data = dapclient.handlers.dap.unpack_dap2_data(f, dataset)

    if das_path is not None:
        with open(das_path) as f:
            das = dapclient.parsers.das.parse_das(f.read())
            dapclient.parsers.das.add_attributes(dataset, das)

    return dataset


def open_dods_url(
    url,
    metadata=False,
    application=None,
    session=None,
    timeout=dapclient.lib.DEFAULT_TIMEOUT,
    verify=True,
):
    """Open a `.dods` response directly, returning a dataset.

    Parameters
    ----------
    url : str
        The url to the `.dods` response.
    metadata : bool, optional
        If True, also fetch the `.das` response and add attributes to the
        dataset.
    application : str, optional
        The application name to send to the server.
    session : requests.Session, optional
        A session object to use for the request.
    timeout : int, optional
        The timeout to use for the request.
    verify : bool, optional
        Whether to verify SSL certificates.
    """
    r = dapclient.net.GET(url, application, session, timeout=timeout)
    dapclient.net.raise_for_status(r)

    dds, data = r.body.split(b"\nData:\n", 1)
    dds = dds.decode(r.content_encoding or "ascii")
    dataset = dapclient.parsers.dds.dds_to_dataset(dds)
    stream = dapclient.handlers.dap.StreamReader(BytesIO(data))
    dataset.data = dapclient.handlers.dap.unpack_dap2_data(stream, dataset)

    if metadata:
        scheme, netloc, path, query, fragment = urlsplit(url)
        dasurl = urlunsplit((scheme, netloc, path[:-4] + "das", query, fragment))
        r = dapclient.net.GET(
            dasurl, application, session, timeout=timeout, verify=verify
        )
        dapclient.net.raise_for_status(r)
        das = dapclient.parsers.das.parse_das(r.text)
        dapclient.parsers.das.add_attributes(dataset, das)

    return dataset


class Functions:
    """Proxy for server-side functions."""

    def __init__(
        self,
        baseurl,
        application=None,
        session=None,
        timeout=dapclient.lib.DEFAULT_TIMEOUT,
    ):
        self.baseurl = baseurl
        self.application = application
        self.session = session
        self.timeout = timeout

    def __getattr__(self, attr):
        return ServerFunction(
            self.baseurl, attr, self.application, self.session, timeout=self.timeout
        )


class ServerFunction:
    """A proxy for a server-side function.

    Instead of returning datasets, the function will return a proxy object,
    allowing nested requests to be performed on the server.
    """

    def __init__(
        self,
        baseurl,
        name,
        application=None,
        session=None,
        timeout=dapclient.lib.DEFAULT_TIMEOUT,
    ):
        self.baseurl = baseurl
        self.name = name
        self.application = application
        self.session = session
        self.timeout = timeout

    def __call__(self, *args):
        params = []
        for arg in args:
            if isinstance(arg, (dapclient.model.DapType, ServerFunctionResult)):
                params.append(arg.id)
            else:
                params.append(dapclient.lib.encode(arg))
        id_ = self.name + "(" + ",".join(params) + ")"
        return ServerFunctionResult(
            self.baseurl, id_, self.application, self.session, timeout=self.timeout
        )


class ServerFunctionResult:
    """A proxy for the result from a server-side function call."""

    def __init__(
        self,
        baseurl,
        id_,
        application=None,
        session=None,
        timeout=dapclient.lib.DEFAULT_TIMEOUT,
    ):
        self.id = id_
        self.dataset = None
        self.application = application
        self.session = session
        self.timeout = timeout

        scheme, netloc, path, query, fragment = urlsplit(baseurl)
        self.url = urlunsplit((scheme, netloc, path + ".dods", id_, None))

    def __getitem__(self, key):
        if self.dataset is None:
            self.dataset = open_dods_url(
                self.url, True, self.application, self.session, self.timeout
            )
        return self.dataset[key]

    def __getattr__(self, name):
        return self[name]


if __name__ == "__main__":
    # fname = '/home/griessbaum/Dropbox/UCSB/dapclient_cpt/dapclient_notebooks/ATL03_20181228015957_13810110_003_01.2var.h5.dmrpp.dmr'
    fname = "/home/griessbaum/Dropbox/UCSB/dapclient_cpt/dapclient_notebooks/data/coads_climatology.nc.dmr"
    ds = open_file(fname)
    print(ds)
