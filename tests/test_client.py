import numpy as np
import pytest

from dapclient.client import open_dods_url, open_url


@pytest.mark.client
def test_metadata():
    dataset = open_url("http://test.opendap.org/dap/data/nc/coads_climatology.nc")
    sst = dataset["SST"]  # or dataset.SST

    assert dataset.name == "coads_climatology%2Enc"
    assert str(type(dataset)) == "<class 'dapclient.model.DatasetType'>"
    assert list(dataset.keys()) == [
        "COADSX",
        "COADSY",
        "TIME",
        "SST",
        "AIRT",
        "UWND",
        "VWND",
    ]
    assert str(type(sst)) == "<class 'dapclient.model.GridType'>"
    assert sst.dimensions == ("TIME", "COADSY", "COADSX")
    assert sst.shape == (12, 90, 180)
    assert str(sst.dtype) == np.dtype(">f4")
    assert sst.TIME.shape == (12,)
    assert str(sst.TIME.dtype) == np.dtype(">f8")
    assert sst.attributes == {
        "_FillValue": -9.99999979e33,
        "history": "From coads_climatology",
        "long_name": "SEA SURFACE TEMPERATURE",
        "missing_value": -9.99999979e33,
        "units": "Deg C",
    }
    assert sst.units == "Deg C"


@pytest.mark.client
def test_grid_data():
    dataset = open_url("http://test.opendap.org/dap/data/nc/coads_climatology.nc")
    sst = dataset["SST"]  # or dataset.SST
    grid = sst[0, 10:14, 10:14]  # this will download data from the server

    assert (
        str(grid) == "<GridType with array 'SST' and maps 'TIME', 'COADSY', 'COADSX'>"
    )
    assert (
        str(grid.array[:].data)
        == """[[[-1.2628571e+00 -9.9999998e+33 -9.9999998e+33 -9.9999998e+33]
  [-7.6916665e-01 -7.7999997e-01 -6.7545450e-01 -5.9571427e-01]
  [ 1.2833333e-01 -5.0000016e-02 -6.3636363e-02 -1.4166667e-01]
  [ 6.3800001e-01  8.9538461e-01  7.2166663e-01  8.1000000e-01]]]"""
    )
    assert (
        str(grid.COADSX[:])
        == "<BaseType with data array([41., 43., 45., 47.], dtype='>f8')>"
    ) or (str(grid.COADSX[:]) == "<BaseType with data array([41., 43., 45., 47.])>")


@pytest.mark.client
def test_grid_subset():
    dataset = open_url("http://test.opendap.org/dap/data/nc/coads_climatology.nc")
    sst = dataset["SST"]  # or dataset.SST
    grid = sst[0, 10:14, 10:14]  # this will download data from the server

    assert np.array_equal(grid.COADSX[:].data, [41.0, 43.0, 45.0, 47.0])


@pytest.mark.client
def test_sst_grid():
    dataset = open_url("http://test.opendap.org/dap/data/nc/coads_climatology.nc")
    sst = dataset["SST"]  # or dataset.SST
    np.array_equal(
        sst.array[0, 10:14, 10:14].data,
        [
            [
                [-1.26285708e00, -9.99999979e33, -9.99999979e33, -9.99999979e33],
                [-7.69166648e-01, -7.79999971e-01, -6.75454497e-01, -5.95714271e-01],
                [1.28333330e-01, -5.00000156e-02, -6.36363626e-02, -1.41666666e-01],
                [6.38000011e-01, 8.95384610e-01, 7.21666634e-01, 8.10000002e-01],
            ]
        ],
    )

    grid = sst[0, 10:14, 10:14]
    assert (
        str(grid) == "<GridType with array 'SST' and maps 'TIME', 'COADSY', 'COADSX'>"
    )

    # This server no longer exists...
    #    dataset = open_url("http://dapper.pmel.noaa.gov/dapper/argo/argo_all.cdp")
    #
    #    assert print(type(dataset.location)) == "<class 'dapclient.model.SequenceType'>"
    #    assert dataset.location.keys() == [
    #        "LATITUDE",
    #        "JULD",
    #        "LONGITUDE",
    #        "_id",
    #        "profile",
    #        "attributes",
    #        "variable_attributes",
    #    ]
    #    my_location = dataset.location[
    #        (dataset.location.LATITUDE > -2)
    #        & (dataset.location.LATITUDE < 2)
    #        & (dataset.location.LONGITUDE > 320)
    #        & (dataset.location.LONGITUDE < 330)
    #    ]
    #
    #    collect = []
    #    for i, id_ in enumerate(my_location["_id"].iterdata()):
    #        print(id_)
    #        collect.append(id_)
    #        if i == 10:
    #            print("...")
    #            break
    #
    #    assert collect == [
    #        1125393,
    #        835304,
    #        839894,
    #        875344,
    #        110975,
    #        864748,
    #        832685,
    #        887712,
    #        962673,
    #        881368,
    #        1127922,
    #    ]
    #    assert len(my_location["_id"].iterdata()) == 623
    #
    #    my_location = my_location[:5]
    #    assert len(my_location["_id"].iterdata()) == 5
    #
    #    from coards import from_udunits
    #
    #    positions = []
    #    prestemps = []
    #    for position in my_location.iterdata():
    #        date = from_udunits(position.JULD.data, position.JULD.units.replace("GMT", "+0:00"))
    #        print(position.LATITUDE.data, position.LONGITUDE.data, date)
    #        print("=" * 40)
    #        i = 0
    #        positions.append([position.LATITUDE.data, position.LONGITUDE.data, date])
    #        lprestemps = []
    #        for pressure, temperature in zip(position.profile.PRES, position.profile.TEMP):
    #            print(pressure, temperature)
    #            lprestemps.append((pressure, temperature))
    #            if i == 10:
    #                prestemps.append(lprestemps)
    #                print("...")
    #                break
    #            i += 1
    #
    #    comparepos = [
    #        [-1.01, 320.019, "2009-05-03 11:42:34+00:00"],
    #        [-0.675, 320.027, "2006-12-25 13:24:11+00:00"],
    #        [-0.303, 320.078, "2007-01-12 11:30:31.001000+00:00"],
    #        [-1.229, 320.095, "2007-04-22 13:03:35.002000+00:00"],
    #        [-1.82, 320.131, "2003-04-09 13:20:03+00:00"],
    #    ]
    #
    #    comparept = [
    #        [
    #            (5.0, 28.59),
    #            (10.0, 28.788),
    #            (15.0, 28.867),
    #            (20.0, 28.916),
    #            (25.0, 28.94),
    #            (30.0, 28.846),
    #            (35.0, 28.566),
    #            (40.0, 28.345),
    #            (45.0, 28.05),
    #            (50.0, 27.595),
    #            (55.0, 27.061),
    #        ],
    #        [
    #            (5.0, 27.675),
    #            (10.0, 27.638),
    #            (15.0, 27.63),
    #            (20.0, 27.616),
    #            (25.0, 27.617),
    #            (30.0, 27.615),
    #            (35.0, 27.612),
    #            (40.0, 27.612),
    #            (45.0, 27.605),
    #            (50.0, 27.577),
    #            (55.0, 27.536),
    #        ],
    #        [
    #            (5.0, 27.727),
    #            (10.0, 27.722),
    #            (15.0, 27.734),
    #            (20.0, 27.739),
    #            (25.0, 27.736),
    #            (30.0, 27.718),
    #            (35.0, 27.694),
    #            (40.0, 27.697),
    #            (45.0, 27.698),
    #            (50.0, 27.699),
    #            (55.0, 27.703),
    #        ],
    #        [
    #            (5.0, 28.634),
    #            (10.0, 28.71),
    #            (15.0, 28.746),
    #            (20.0, 28.758),
    #            (25.0, 28.755),
    #            (30.0, 28.747),
    #            (35.0, 28.741),
    #            (40.0, 28.737),
    #            (45.0, 28.739),
    #            (50.0, 28.748),
    #            (55.0, 28.806),
    #        ],
    #        [
    #            (5.1, 28.618),
    #            (9.1, 28.621),
    #            (19.4, 28.637),
    #            (29.7, 28.662),
    #            (39.6, 28.641),
    #            (49.6, 28.615),
    #            (59.7, 27.6),
    #            (69.5, 26.956),
    #            (79.5, 26.133),
    #            (89.7, 23.937),
    #            (99.2, 22.029),
    #        ],
    #    ]
    #
    #    collect = []
    #    for value in my_location.profile.PRES.iterdata():
    #        collect.append(value[:10])
    #    assert collect == [
    #        [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
    #        [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
    #        [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
    #        [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
    #        [
    #            5.0999999,
    #            9.1000004,
    #            19.4,
    #            29.700001,
    #            39.599998,
    #            49.599998,
    #            59.700001,
    #            69.5,
    #            79.5,
    #            89.699997,
    #        ],
    #    ]
    #


@pytest.mark.client
def test_grid_coords():
    dataset = open_url("http://test.opendap.org/dap/data/nc/coads_climatology.nc")
    new_dataset = dataset.functions.geogrid(dataset.SST, 10, 20, -10, 60)
    assert new_dataset.SST.shape == (12, 12, 21)
    assert np.array_equal(
        new_dataset.SST.COADSY[:],
        list(
            reversed(
                [
                    -11.0,
                    -9.0,
                    -7.0,
                    -5.0,
                    -3.0,
                    -1.0,
                    1.0,
                    3.0,
                    5.0,
                    7.0,
                    9.0,
                    11.0,
                ]
            )
        ),
    )
    assert np.array_equal(
        new_dataset.SST.COADSX[:],
        [
            21.0,
            23.0,
            25.0,
            27.0,
            29.0,
            31.0,
            33.0,
            35.0,
            37.0,
            39.0,
            41.0,
            43.0,
            45.0,
            47.0,
            49.0,
            51.0,
            53.0,
            55.0,
            57.0,
            59.0,
            61.0,
        ],
    )


@pytest.mark.client
def test_shapes():
    dataset = open_url(
        "http://test.opendap.org/dap/data/nc/coads_climatology.nc?SST[0:3:11][0:1:89][0:1:179]"
    )
    assert dataset.SST.shape == (4, 90, 180)


# def test_fsu():
#    dataset = open_url(
#        "http://hycom.coaps.fsu.edu:8080/thredds/dodsC/las/dynamic/data_A5CDC5CAF9D810618C39646350F727FF.jnl_expr_%7B%7D%7Blet%20A=SSH*2%7D?A"
#    )
#    assert dataset.keys() == ["A"]


@pytest.mark.client
def test_dods():
    dataset = open_dods_url(
        "http://test.opendap.org/dap/data/nc/coads_climatology.nc.dods?SST[0:3:11][0:1:89][0:1:179]"
    )

    dataset = open_dods_url(
        "http://test.opendap.org/dap/data/nc/coads_climatology.nc.dods?SST[0:3:11][0:1:89][0:1:179]",
        metadata=True,
    )
    assert (
        dataset.attributes["NC_GLOBAL"]["history"]
        == "FERRET V4.30 (debug/no GUI) 15-Aug-96"
    )
