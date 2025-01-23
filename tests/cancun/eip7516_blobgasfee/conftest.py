"""Fixtures for the EIP-7516 blobgasfee tests."""

import pytest


@pytest.fixture
def tx_gas_limit() -> int:  # noqa: D103
    return 3_000_000
