import os
import sys
import traceback
from pathlib import Path


def smoke_log(message):
    target = os.environ.get('JAVAN_CI_SMOKE_LOG')
    if target:
        with Path(target).open('a', encoding='utf-8') as stream:
            stream.write(str(message) + '\n')


def main():
    from javan.app import run
    from javan.smoke import run_smoke, run_accounting_probe
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ('--accounting-probe-seed', '--accounting-probe-write', '--accounting-probe-read'):
        return run_accounting_probe(args[0].rsplit('-', 1)[-1], args[1])
    return run_smoke() if '--smoke-test' in args else run()


if __name__ == '__main__':
    # Only synthetic CI runs enable this diagnostic path. Avoid a windowed
    # bootloader exception dialog blocking the test until its timeout.
    if os.environ.get('JAVAN_CI_SMOKE_LOG'):
        def hook(exc_type, exc, tb):
            smoke_log(''.join(traceback.format_exception(exc_type, exc, tb)))
        sys.excepthook = hook
        try:
            smoke_log('Starting ' + ('smoke test' if '--smoke-test' in sys.argv else 'probe'))
            code = main()
            smoke_log('Exit code: ' + str(code))
        except Exception:
            smoke_log(traceback.format_exc())
            code = 1
        raise SystemExit(code)
    raise SystemExit(main())
