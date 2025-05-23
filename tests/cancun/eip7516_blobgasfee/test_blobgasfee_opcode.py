"""
abstract: Tests [EIP-7516: BLOBBASEFEE opcode](https://eips.ethereum.org/EIPS/eip-7516)
    Test BLOBGASFEE opcode [EIP-7516: BLOBBASEFEE opcode](https://eips.ethereum.org/EIPS/eip-7516).

"""  # noqa: E501

import pytest

from ethereum_test_tools import (
    Account,
    Address,
    Alloc,
    Bytecode,
    Environment,
    StateTestFiller,
    Storage,
    Transaction,
)
from ethereum_test_tools import Opcodes as Op

REFERENCE_SPEC_GIT_PATH = "EIPS/eip-7516.md"
REFERENCE_SPEC_VERSION = "2ade0452efe8124378f35284676ddfd16dd56ecd"

BLOBBASEFEE_GAS = 2


@pytest.fixture
def call_gas() -> int:
    """Amount of gas to use when calling the callee code."""
    return 0xFFFF


@pytest.fixture
def callee_code() -> Bytecode:
    """Bytecode under test, by default, only call the BLOBBASEFEE opcode."""
    return Op.BLOBBASEFEE + Op.STOP


@pytest.fixture
def callee_address(pre: Alloc, callee_code: Bytecode) -> Address:
    """Address of the account containing the bytecode under test."""
    return pre.deploy_contract(callee_code)


@pytest.fixture
def caller_code(
    call_gas: int,
    callee_address: Address,
) -> Bytecode:
    """Bytecode used to call the bytecode containing the BLOBBASEFEE opcode."""
    return Op.SSTORE(123, Op.CALL(gas=call_gas, address=callee_address))


@pytest.fixture
def caller_pre_storage() -> Storage:
    """Storage of the account containing the bytecode that calls the test contract."""
    return Storage()


@pytest.fixture
def caller_address(pre: Alloc, caller_code: Bytecode, caller_pre_storage) -> Address:
    """Address of the account containing the bytecode that calls the test contract."""
    return pre.deploy_contract(caller_code)


@pytest.fixture
def tx(pre: Alloc, caller_address: Address, tx_gas_limit: int) -> Transaction:
    """
    Prepare test transaction, by setting the destination account, the
    transaction value, the transaction gas limit, and the transaction data.
    """
    return Transaction(
        sender=pre.fund_eoa(),
        gas_limit=tx_gas_limit,
        to=caller_address,
    )


@pytest.mark.parametrize(
    "callee_code,call_fails",
    [
        pytest.param(Op.BLOBBASEFEE * 1024, False, id="no_stack_overflow"),
        pytest.param(Op.BLOBBASEFEE * 1025, True, id="stack_overflow"),
    ],
)
@pytest.mark.valid_from("Cancun")
def test_blobbasefee_stack_overflow(
    state_test: StateTestFiller,
    pre: Alloc,
    caller_address: Address,
    callee_address: Address,
    tx: Transaction,
    call_fails: bool,
):
    """Tests that the BLOBBASEFEE opcode produces a stack overflow by using it repeatedly."""
    post = {
        caller_address: Account(
            storage={123: 0 if call_fails else 1},
        ),
        callee_address: Account(
            balance=0,
        ),
    }
    state_test(
        env=Environment(),
        pre=pre,
        tx=tx,
        post=post,
    )


@pytest.mark.parametrize(
    "call_gas,call_fails",
    [
        pytest.param(BLOBBASEFEE_GAS, False, id="enough_gas"),
        pytest.param(BLOBBASEFEE_GAS - 1, True, id="out_of_gas"),
    ],
)
@pytest.mark.valid_from("Cancun")
def test_blobbasefee_out_of_gas(
    state_test: StateTestFiller,
    pre: Alloc,
    caller_address: Address,
    callee_address: Address,
    tx: Transaction,
    call_fails: bool,
):
    """Tests that the BLOBBASEFEE opcode fails with insufficient gas."""
    post = {
        caller_address: Account(
            storage={123: 0 if call_fails else 1},
        ),
        callee_address: Account(
            balance=0,
        ),
    }
    state_test(
        env=Environment(),
        pre=pre,
        tx=tx,
        post=post,
    )
