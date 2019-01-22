from functools import partial

import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--network', action='store_true', dest="network",
        default=False, help="allow network related tests to run")


def mark_network(config, func):
    """Decorator to add a 'net' mark and skip the test unless --network is passed."""
    skip_func = pytest.mark.skipif(
        not config.option.network,
        reason="needs --network option to run")
    return skip_func(pytest.mark.net(func))


def pytest_configure(config):
    pytest.mark_network = partial(mark_network, config)
