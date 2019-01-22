import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--network', action='store_true', dest="network",
        default=False, help="enable network mark decorated tests")


def pytest_configure(config):
    pytest.mark.network = pytest.mark.skipif(
        not config.option.network,
        reason="needs --network option to run")
