"""Command-line interface for the clock application."""
import argparse
import time

from .display import run_clock
from .config import get_settings
from .sensors import TemperatureReader

def main():
    settings = get_settings()
    block_orientation = settings.integer('hardware', 'block_orientation', -90, -90, 90)
    if block_orientation not in (0, 90, -90):
        block_orientation = -90
    parser = argparse.ArgumentParser(description='MAX7219 LED matrix clock (8 panels)')
    parser.add_argument('--cascaded', '-n', type=int, default=settings.integer('hardware', 'panel_count', 8, 1, 32), help='Number of panels (default: 8)')
    parser.add_argument('--block-orientation', type=int, default=block_orientation, choices=[0, 90, -90], help='Block orientation')
    parser.add_argument('--rotate', type=int, default=settings.integer('hardware', 'rotation', 0, 0, 3), choices=[0, 1, 2, 3], help='Rotate display')
    parser.add_argument('--reverse-order', dest='reverse_order', action='store_true', default=settings.boolean('hardware', 'reverse_order', False), help='Reverse panel order')
    parser.add_argument('--no-blink', dest='no_blink', action='store_true', default=not settings.boolean('clock', 'blink_colon', True), help='Disable blinking colon')
    parser.add_argument('--seconds', dest='seconds', action='store_true', default=settings.boolean('clock', 'show_seconds', False), help='Show seconds')
    parser.add_argument('--12h', dest='use_12h', action='store_true', default=not settings.boolean('clock', 'format_24h', True), help='Use 12-hour format instead of 24-hour')
    parser.add_argument('--i2c-address', dest='i2c_address', default=settings.get('hardware', 'i2c_address', '0x76'), help='I2C address for BME280 (hex)')
    parser.add_argument('--i2c-port', dest='i2c_port', type=int, default=settings.integer('hardware', 'i2c_port', 1, 0, 16), help='I2C bus number (default 1)')
    parser.add_argument('--test-bme', dest='test_bme', action='store_true', help='Run a BME280 test read and exit')
    parser.add_argument('--quiet', dest='quiet', action='store_true', help='Suppress debug output')
    parser.add_argument('--verbose', dest='verbose', action='store_true', help='Show debug output')
    parser.add_argument('--show-temp-only', dest='show_temp_only', action='store_true', help='Display temperature only')

    args = parser.parse_args()

    # parse i2c address string like 0x76
    try:
        i2c_addr = int(args.i2c_address, 0)
    except Exception:
        i2c_addr = 0x76

    if args.test_bme:
        tr = TemperatureReader(i2c_addr=i2c_addr, i2c_port=args.i2c_port, verbose=True)
        print(f"Test mode. Backend: {tr.backend}")
        try:
            while True:
                val = tr.read()
                print(f"BME temp: {val}")
                time.sleep(2)
        except KeyboardInterrupt:
            print('Test stopped')
            return

    verbose_flag = args.verbose or args.test_bme
    run_clock(args.cascaded, args.block_orientation, args.rotate, args.reverse_order,
              show_seconds=args.seconds, blink=not args.no_blink, fmt24=not args.use_12h,
              i2c_addr=i2c_addr, i2c_port=args.i2c_port, verbose=verbose_flag, show_temp_only=args.show_temp_only)


if __name__ == "__main__":
    main()
