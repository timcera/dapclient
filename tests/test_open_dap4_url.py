import pytest

import dapclient.client


def test_coads():
    url = "dap4://test.opendap.org/opendap/hyrax/data/nc/coads_climatology.nc"
    pydap_ds = dapclient.client.open_url(url)
    data = pydap_ds["COADSX"][10:12:1]
    assert data is not None


@pytest.mark.skip(reason="takes a really long time")
def test_groups():
    url = "dap4://test.opendap.org:8080/opendap/dmrpp_test_files/ATL03_20181228015957_13810110_003_01.2var.h5.dmrpp"
    pydap_ds = dapclient.client.open_url(url)
    data = pydap_ds["/gt1r/bckgrd_atlas/bckgrd_int_height"][:10]
    assert data is not None


@pytest.mark.skip(reason="bug in testserver")
def test_maps():
    url = "dap4://test.opendap.org:8080/opendap/hyrax/data/nc/coads_climatology.nc"
    pydap_ds = dapclient.client.open_url(url)
    data = pydap_ds["SST"][0:2:1, 40:42:1, 1:10:1]
    assert data is not None


if __name__ == "__main__":
    test_maps()
