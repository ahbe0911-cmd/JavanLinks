import sys
from javan.app import run
from javan.smoke import run_smoke, run_accounting_probe

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ('--accounting-probe-write', '--accounting-probe-read'):
        raise SystemExit(run_accounting_probe(args[0].rsplit('-', 1)[-1], args[1]))
    raise SystemExit(run_smoke() if '--smoke-test' in args else run())
