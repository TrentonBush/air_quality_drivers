import pytest
from drivers.hdc1080 import MockHDC1080, TemperatureEncoder, HumidityEncoder
from drivers.i2c_base import MockSMBus, Field


@pytest.fixture(scope="class")
def mocked_HDC1080():
    # calibration and data values are same as in test__apply_calibration
    # converted with:
    # (expected_value).to_bytes(3, 'big').hex()
    registers = {
        # temperature: -40 °C, humidity: 0 %RH.
        # Concatenated to simulate burst read for .data register
        0x00: [0x00, 0x00, 0x00, 0x00],
        0x01: [0x00, 0x00],  # humidity: 0 %RH
        # config: reset=False, heater_on=False, measure_both=True,
        # battery_low=True, temp_res_bits=14, rh_res_bits=14
        0x02: [0x18, 0x00],
        0xFB: [0x03, 0x03, 0x02, 0x02, 0x01, 0x01],  # serial_id
        0xFE: [0x54, 0x49],  # manufacturer_id
        0xFF: [0x10, 0x50],  # device_id
    }
    smb = MockSMBus(registers)
    yield MockHDC1080(smb)


def test_TemperatureEncoder_decode__x_and_y_intercepts():
    enc = TemperatureEncoder()
    dummyfield = Field("asdf")
    # y intercept
    expected = -40.0
    actual = enc.decode(b"\x00\x00", dummyfield)
    assert actual == expected  # shouldnt be any roundoff error

    # x intercept
    expected = 0.0
    byte_val = int(round(40.0 * 2 ** 16 / 165.0)).to_bytes(2, "big")
    actual = enc.decode(byte_val, dummyfield)
    tol = 165 / 2 ** 16  # resolution of transfer function (measurement is 4x coarser)
    assert actual == pytest.approx(expected, abs=tol)


def test_HumidityEncoder_decode__x_and_y_intercepts():
    enc = HumidityEncoder()
    dummyfield = Field("asdf")
    # y intercept
    expected = 0.0
    actual = enc.decode(b"\x00\x00", dummyfield)
    assert actual == expected  # shouldnt be any roundoff error

    # x intercept
    expected = 100.0 - (100 / 2 ** 16)
    byte_val = b"\xFF\xFF"  # 2**16 - 1
    actual = enc.decode(byte_val, dummyfield)
    tol = 100 / 2 ** 16  # resolution of transfer function (measurement is 4x coarser)
    assert actual == pytest.approx(expected, abs=tol)


def test_HDC1080_reads(mocked_HDC1080):
    """test if I set up the registers/fields correctly"""
    hdc = mocked_HDC1080
    hdc.data.read()
    expected = {"temperature": -40.0, "humidity": 0.0}
    actual = hdc.data.values
    assert actual == expected

    hdc.temperature.read()
    expected = {"temperature": -40.0}
    actual = hdc.temperature.values
    assert actual == expected

    hdc.humidity.read()
    expected = {"humidity": 0.0}
    actual = hdc.humidity.values
    assert actual == expected

    hdc.config.read()
    expected = dict(
        reset=False,
        heater_on=False,
        measure_both=True,
        battery_low=True,
        temp_res_bits=14,
        rh_res_bits=14,
        reserved=0,
    )
    actual = hdc.config.values
    assert actual == expected

    hdc.device_id.read()
    expected = {"device_id": 0x1050}
    actual = hdc.device_id.values
    assert actual == expected

    hdc.manufacturer_id.read()
    expected = {"manufacturer_id": 0x5449}
    actual = hdc.manufacturer_id.values
    assert actual == expected

    hdc.serial_id.read()
    expected = {"serial_id": 0x0303020201}
    actual = hdc.serial_id.values
    assert actual == expected


def test_HDC1080_Config__validation(mocked_HDC1080):
    hdc = mocked_HDC1080
    bad_resolution = 420
    with pytest.raises(ValueError):
        hdc.config.write(temp_resolution_bits=bad_resolution)
    with pytest.raises(ValueError):
        hdc.config.write(humidity_resolution_bits=bad_resolution)


def test_HDC1080_Config__write(mocked_HDC1080):
    hdc = mocked_HDC1080
    expected = dict(
        reset=True,
        heater_on=True,
        measure_both=False,
        battery_low=False,
        temp_res_bits=11,
        rh_res_bits=8,
        reserved=0,
    )
    hdc.config.write(
        soft_reset=True,
        heater_on=True,
        measure_both=False,
        temp_resolution_bits=11,
        humidity_resolution_bits=8,
    )
    actual = hdc._i2c_read(hdc.hardware.registers["config"])
    actual = hdc.hardware.registers["config"]._raw_bytes_to_field_values(actual)
    assert actual == expected


def test_HDC1080_measurement_duration__simultaneous(mocked_HDC1080):
    hdc = mocked_HDC1080
    hdc.config.read()
    expected = (6.35 + 6.5 + 1) / 1000
    actual = hdc.measurement_duration
    # tolerance is 0.1 millisecond
    assert actual == pytest.approx(expected, abs=1e-4)


def test_HDC1080_measurement_duration__separate(mocked_HDC1080):
    hdc = mocked_HDC1080
    hdc.config.write(measure_both=False, humidity_resolution_bits=8)
    expected = (6.35 + 1) / 1000
    actual = hdc.measurement_duration
    assert actual == expected
