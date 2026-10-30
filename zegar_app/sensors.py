"""BME280 sensor backends (CircuitPython, smbus2, and direct SMBus)."""
import os
import sys
import time

class TemperatureReader:
    """Wykrywa dostępny backend BME280 i udostępnia metodę read().
    Zwraca słownik z danymi lub None. Importy i inicjalizacje wykonywane raz.
    """
    def __init__(self, i2c_addr=0x76, i2c_port=1, verbose=True):
        self.backend = None
        self._reader = None
        self._addr = i2c_addr
        self._port = i2c_port
        self.verbose = verbose

        if self.verbose:
            print(f"TemperatureReader init: addr=0x{self._addr:02x} port={self._port}", file=sys.stderr)

        try:
            import board
            import busio
            import adafruit_bme280

            i2c = busio.I2C(board.SCL, board.SDA)
            bme = adafruit_bme280.Adafruit_BME280_I2C(i2c)
            self.backend = 'adafruit'
            def _read_adafruit():
                return {
                    'temp': bme.temperature,
                    'hum': bme.humidity,
                    'press': bme.pressure
                }
            self._reader = _read_adafruit
            if self.verbose:
                print("Using adafruit_bme280 backend", file=sys.stderr)
        except Exception as e:
            if self.verbose:
                print(f"adafruit backend failed: {e}", file=sys.stderr)
            # continue to try other backends

        if not self._reader:
            try:
                import smbus2
                import bme280

                # check i2c device path
                devpath = f"/dev/i2c-{self._port}"
                if not os.path.exists(devpath):
                    if self.verbose:
                        print(f"I2C device {devpath} not found", file=sys.stderr)
                    raise FileNotFoundError(devpath)

                bus = smbus2.SMBus(self._port)
                try:
                    calib = bme280.load_calibration_params(bus, self._addr)
                except Exception as e:
                    if self.verbose:
                        print(f"bme280.load_calibration_params failed for addr 0x{self._addr:02x}: {e}", file=sys.stderr)
                    # try alternate common address
                    alt = 0x77 if self._addr == 0x76 else 0x76
                    if self.verbose:
                        print(f"Trying alternate address 0x{alt:02x}", file=sys.stderr)
                    calib = bme280.load_calibration_params(bus, alt)
                    self._addr = alt

                def _read_bme():
                    data = bme280.sample(bus, self._addr, calib)
                    return {
                        'temp': data.temperature,
                        'hum': data.humidity,
                        'press': data.pressure
                    }

                self.backend = 'smbus'
                self._reader = _read_bme
            except Exception as e:
                if self.verbose:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                # try a direct smbus-only implementation (no bme280 package)
                try:
                    import smbus2 as _smbus

                    devpath = f"/dev/i2c-{self._port}"
                    if not os.path.exists(devpath):
                        if self.verbose:
                            print(f"I2C device {devpath} not found for direct backend", file=sys.stderr)
                        raise FileNotFoundError(devpath)

                    bus = _smbus.SMBus(self._port)

                    # verify chip id
                    CHIP_ID_REG = 0xD0
                    chip_id = bus.read_byte_data(self._addr, CHIP_ID_REG)
                    if self.verbose:
                        print(f"Chip ID at 0x{self._addr:02x}: 0x{chip_id:02x}", file=sys.stderr)

                    # read temperature calibration params (T1,T2,T3)
                    def _read_u16_le(reg):
                        lo = bus.read_byte_data(self._addr, reg)
                        hi = bus.read_byte_data(self._addr, reg + 1)
                        return (hi << 8) | lo

                    def _read_s16_le(reg):
                        val = _read_u16_le(reg)
                        if val & 0x8000:
                            return -((~val & 0xFFFF) + 1)
                        return val

                    dig_T1 = _read_u16_le(0x88)
                    dig_T2 = _read_s16_le(0x8A)
                    dig_T3 = _read_s16_le(0x8C)

                    if self.verbose:
                        print(f"Calibration T1={dig_T1} T2={dig_T2} T3={dig_T3}", file=sys.stderr)

                    # configure sensor: set humidity oversampling (must write before ctrl_meas)
                    try:
                        # osrs_h = 1 (oversampling x1)
                        bus.write_byte_data(self._addr, 0xF2, 0x01)
                        # osrs_t=1, osrs_p=1, mode=3 (normal)
                        bus.write_byte_data(self._addr, 0xF4, 0x27)
                        # config register set to default (standby 0, filter off)
                        bus.write_byte_data(self._addr, 0xF5, 0x00)
                        if self.verbose:
                            print("Configured BME280 ctrl registers (osrs, mode)", file=sys.stderr)
                    except Exception as e:
                        if self.verbose:
                            print(f"Failed to configure ctrl registers: {e}", file=sys.stderr)

                    def _read_raw_temp():
                        msb = bus.read_byte_data(self._addr, 0xFA)
                        lsb = bus.read_byte_data(self._addr, 0xFB)
                        xlsb = bus.read_byte_data(self._addr, 0xFC)
                        raw = (msb << 12) | (lsb << 4) | (xlsb >> 4)
                        return raw

                    # t_fine needs to be recalculated each read
                    def _read_temp_compensated():
                        # trigger a forced measurement to ensure fresh data
                        try:
                            # osrs_t=1, osrs_p=1, mode=1 (forced)
                            bus.write_byte_data(self._addr, 0xF4, 0x25)
                        except Exception:
                            pass
                        # wait for measurement to complete (max ~10-50ms depending on oversampling)
                        time.sleep(0.06)

                        raw_t = _read_raw_temp()
                        var1 = (raw_t / 16384.0 - dig_T1 / 1024.0) * dig_T2
                        var2 = ((raw_t / 131072.0 - dig_T1 / 8192.0) ** 2) * dig_T3
                        t_fine = var1 + var2
                        T = t_fine / 5120.0
                        return {'temp': float(T)}

                    self.backend = 'smbus-direct'
                    self._reader = _read_temp_compensated
                    if self.verbose:
                        print("Using smbus-direct backend", file=sys.stderr)
                except Exception:
                    if self.verbose:
                        print("Direct smbus backend failed", file=sys.stderr)
                        import traceback
                        traceback.print_exc(file=sys.stderr)
                    pass

    def read(self):
        if not self._reader:
            return None
        try:
            return self._reader()
        except Exception:
            if self.verbose:
                import traceback
                traceback.print_exc(file=sys.stderr)
            return None
