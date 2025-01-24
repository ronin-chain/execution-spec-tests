"""Fixtures for the EIP-6780 selfdestruct tests."""

import pytest

from ethereum_test_tools import Alloc, Environment, EOA


@pytest.fixture
def tx_gas_limit() -> int:  # noqa: D103
    return 3_000_000


@pytest.fixture
def sender(pre: Alloc) -> EOA:
    """EOA that will be used to send transactions."""
    return pre.fund_eoa()


@pytest.fixture
def env() -> Environment:
    """Environment for all tests."""
    return Environment()
