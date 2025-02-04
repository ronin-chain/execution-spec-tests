"""Fixtures for the EIP-6780 selfdestruct tests."""

import eth_account
import pytest

from ethereum_test_tools import EOA, Address, Alloc, Environment


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


@pytest.fixture
def selfdestruct_recipient_address() -> Address:
    """Address that can receive a SELFDESTRUCT operation."""
    account = eth_account.Account.create()
    return Address(account.address)
