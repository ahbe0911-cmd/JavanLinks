import sys
from javan.app import run
from javan.smoke import run_smoke

if __name__ == '__main__':
    raise SystemExit(run_smoke() if '--smoke-test' in sys.argv[1:] else run())
