.. image:: https://github.com/timcera/dapclient/actions/workflows/python-package.yml/badge.svg
    :alt: Tests
    :target: https://github.com/timcera/dapclient/actions/workflows/python-package.yml
    :height: 20

.. image:: https://img.shields.io/coveralls/github/timcera/dapclient
    :alt: Test Coverage
    :target: https://coveralls.io/r/timcera/dapclient?branch=master
    :height: 20

.. image:: https://img.shields.io/pypi/v/dapclient.svg
    :alt: Latest release
    :target: https://pypi.python.org/pypi/dapclient/
    :height: 20

.. image:: http://img.shields.io/pypi/l/dapclient.svg
    :alt: BSD-3 clause license
    :target: https://pypi.python.org/pypi/dapclient/
    :height: 20

.. image:: http://img.shields.io/pypi/dd/dapclient.svg
    :alt: dapclient downloads
    :target: https://pypi.python.org/pypi/dapclient/
    :height: 20

.. image:: https://img.shields.io/pypi/pyversions/dapclient
    :alt: PyPI - Python Version
    :target: https://pypi.org/project/dapclient/
    :height: 20

dapclient - Quick Guide
=======================
dapclient is a client-only fork of the venerable pydap. It implements the
Opendap/DODS protocol.  You can use dapclient to access scientific data on the
internet without having to download it; instead, you work with special array
and iterable objects that download data on-the-fly as necessary, saving
bandwidth and time.

Why fork pydap?
---------------
* Simplify the codebase by remove the server side code
* Update the code to use modern python 3.8+
* Up-to-date pypi and conda packages

This version has no additional features, and it only has a few tests.  My
immediate goal is to have pip and conda packages to support my tsgettoolbox
package.  I will add tests and features as time (and pull requests!) allow.

Quickstart
----------
You can install the latest version using
[pip](http://pypi.python.org/pypi/pip). After [installing
pip](http://www.pip-installer.org/en/latest/installing.html) you can
install dapclient with this command::

    $ pip install dapclient

Also maintained on my [conda channel](https://anaconda.org/timcera/dapclient)::

    $ conda install -c timcera dapclient

This will install dapclient together with all the required
dependencies. You can now open any remotely served dataset, and dapclient
will download the accessed data on-the-fly as needed::

    >>> from dapclient.client import open_url
    >>> dataset = open_url('http://test.opendap.org/dap/data/nc/coads_climatology.nc')
    >>> var = dataset['SST']
    >>> var.shape
    (12, 90, 180)
    >>> var.dtype
    dtype('>f4')
    >>> data = var[0,10:14,10:14]  # this will download data from the server
    >>> data
    <GridType with array 'SST' and maps 'TIME', 'COADSY', 'COADSX'>
    >>> print(data.data)
    [array([[[ -1.26285708e+00,  -9.99999979e+33,  -9.99999979e+33, -9.99999979e+33],
            [ -7.69166648e-01,  -7.79999971e-01,  -6.75454497e-01, -5.95714271e-01],
            [  1.28333330e-01,  -5.00000156e-02,  -6.36363626e-02, -1.41666666e-01],
            [  6.38000011e-01,   8.95384610e-01,   7.21666634e-01, 8.10000002e-01]]], dtype=float32),
               array([ 366.]),
               array([-69., -67., -65., -63.]),
               array([ 41.,  43.,  45.,  47.])]

For more information, please check the documentation on [using dapclient
as a client](https://timcera.bitbucket.io/dapclient/client.html).
