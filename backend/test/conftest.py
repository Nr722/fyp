# test/conftest.py
import os
import pytest

def pytest_sessionfinish(session, exitstatus):
    """
    Hook called by pytest after the entire test session finishes.
    Forces an immediate OS exit to cleanly bypass the C-extension thread 
    teardown bug in the diplomacy/matplotlib environment.
    """
    # Force close any remaining open matplotlib figures just to be safe
    try:
        import matplotlib.pyplot as plt
        plt.close('all')
    except ImportError:
        pass

    # Flush output streams so you don't lose any final test reporting lines
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Pre-emptively kill the process with the proper pytest return code
    os._exit(exitstatus)