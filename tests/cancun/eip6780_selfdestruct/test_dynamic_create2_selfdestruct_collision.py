"""
Suicide scenario requested test
https://github.com/ethereum/execution-spec-tests/issues/381.
"""

from typing import Dict, SupportsBytes, Union

import pytest

from ethereum_test_forks import Cancun, Fork
from ethereum_test_tools import (
    EOA,
    Account,
    Address,
    Alloc,
    Block,
    BlockchainTestFiller,
    Bytecode,
    Conditional,
    Environment,
    Initcode,
    StateTestFiller,
    Transaction,
    YulCompiler,
    compute_create2_address,
)
from ethereum_test_tools.vm.opcode import Opcodes as Op

REFERENCE_SPEC_GIT_PATH = "EIPS/eip-6780.md"
REFERENCE_SPEC_VERSION = "2f8299df31bb8173618901a03a8366a3183479b0"


@pytest.fixture
def create2_salt() -> int:  # noqa: D103
    return 1


@pytest.fixture
def create2_constructor_worked() -> int:  # noqa: D103
    return 1


@pytest.fixture
def selfdestruct_contract_init_balance() -> int:  # noqa: D103
    return 1


@pytest.fixture
def selfdestruct_contract_bytecode(
    yul: YulCompiler,
    selfdestruct_recipient_address: Address,
    create2_storage_contract_address: Address,
    create2_constructor_worked: int,
) -> Bytecode:
    """
    Contract code that performs operations based on the calldata.
    The contract can perform a SELFDESTRUCT operation, or revert the constructor operations of the
    initcode to mimic a pre-existing contract before the CREATE2.
    """
    return yul(
        f"""
        {{
            let operation := calldataload(0)

            switch operation
            case 0 /* SELFDESTRUCT */ {{
                selfdestruct({selfdestruct_recipient_address})
            }}
            case 1 /* revert constructor to mimic a pre-existing contract before the CREATE2 */ {{
                sstore({create2_constructor_worked}, 0)
                pop(call(gaslimit(), {create2_storage_contract_address}, 0, 0, 0, 0, 0))
            }}
            default /* unsupported operation */ {{
                stop()
            }}
        }}
        """
    )


@pytest.fixture
def selfdestruct_contract_initcode_prefix(
    create2_constructor_worked: int, create2_storage_contract_address: Address
) -> Bytecode:
    """
    initcode_prefix that sets the create2_constructor_worked storage key and calls the storage
    contract to mark the constructor worked.
    """
    return (
        Op.SSTORE(create2_constructor_worked, 1)
        + Op.MSTORE(0, b"\x00" * 31 + b"\x01")
        + Op.CALL(Op.GAS(), create2_storage_contract_address, 0, 0, 32, 0, 0)
    )


@pytest.fixture
def selfdestruct_contract_initcode(
    selfdestruct_contract_bytecode: Bytecode, selfdestruct_contract_initcode_prefix: Bytecode
) -> Initcode:
    """Initcode of the selfdestruct contract."""
    return Initcode(
        deploy_code=selfdestruct_contract_bytecode,
        initcode_prefix=selfdestruct_contract_initcode_prefix,
    )


@pytest.fixture
def selfdestruct_contract_address(
    pre: Alloc,
    sender: EOA,
    create2_dest_already_in_state: bool,
    selfdestruct_contract_initcode: Initcode,
    selfdestruct_contract_init_balance: int,
    deployer_contract_address: Address,
    create2_salt: int,
    tx_gas_limit: int,
) -> Address:
    """Address of the selfdestruct contract."""
    create2_address = compute_create2_address(
        deployer_contract_address, create2_salt, selfdestruct_contract_initcode
    )

    if create2_dest_already_in_state:  # Mimic a pre-existing contract before the CREATE2
        # Deploy the contract by calling the deployer contract
        deploy_tx = Transaction(
            sender=sender,
            to=deployer_contract_address,
            data=selfdestruct_contract_initcode,
            gas_limit=tx_gas_limit,
            value=selfdestruct_contract_init_balance,
        )
        print(
            "Calling the deployer contract to deploy the selfdestruct contract, create2_address: ",
            create2_address,
        )
        pre.send_wait_transaction(deploy_tx)

        # Call the contract to revert the constructor
        revert_constructor_tx = Transaction(
            sender=sender,
            to=create2_address,
            data=b"\x00" * 31 + b"\x01",
            gas_limit=tx_gas_limit,
            value=0,
        )
        print("Calling the selfdestruct contract to revert the constructor")
        pre.send_wait_transaction(revert_constructor_tx)

    return create2_address


@pytest.fixture
def deployer_contract_bytecode(create2_salt: int) -> Bytecode:
    """Contract code that performs a CREATE2 operation."""
    return (
        Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.MSTORE(
            0,
            Op.CREATE2(Op.SELFBALANCE(), 0, Op.CALLDATASIZE(), create2_salt),
        )
        + Op.RETURN(0, 32)
    )


@pytest.fixture
def deployer_contract_address(pre: Alloc, deployer_contract_bytecode: Bytecode) -> Address:
    """Address of the deployer contract."""
    return pre.deploy_contract(deployer_contract_bytecode)


@pytest.fixture
def create2_storage_contract_bytecode() -> Bytecode:
    """Contract code that sets a storage key to identify the constructor worked."""
    return Op.SSTORE(1, Op.CALLDATALOAD(0))


@pytest.fixture
def create2_storage_contract_init_balance() -> int:  # noqa: D103
    return 700_000


@pytest.fixture
def create2_storage_contract_address(
    pre: Alloc,
    create2_storage_contract_bytecode: Bytecode,
    create2_storage_contract_init_balance: int,
) -> Address:
    """Address of the create2 storage contract."""
    return pre.deploy_contract(
        create2_storage_contract_bytecode, balance=create2_storage_contract_init_balance
    )


@pytest.mark.valid_from("Paris")
@pytest.mark.parametrize(
    "create2_dest_already_in_state",
    (True, False),
)
@pytest.mark.parametrize(
    "call_create2_contract_in_between,call_create2_contract_at_the_end",
    [
        (True, True),
        (True, False),
        (False, True),
    ],
)
def test_dynamic_create2_selfdestruct_collision(
    env: Environment,
    pre: Alloc,
    fork: Fork,
    sender: EOA,
    create2_dest_already_in_state: bool,
    call_create2_contract_in_between: bool,
    call_create2_contract_at_the_end: bool,
    tx_gas_limit: int,
    selfdestruct_contract_address: Address,
    selfdestruct_contract_bytecode: Bytecode,
    selfdestruct_contract_init_balance: int,
    selfdestruct_contract_initcode: Initcode,
    selfdestruct_recipient_address: Address,
    create2_storage_contract_address: Address,
    deployer_contract_address: Address,
    state_test: StateTestFiller,
):
    """
    Dynamic Create2->Suicide->Create2 collision scenario.

    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then on a different call, in the same tx, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract   <=== Covered in this test
            1) and create2 contract already in the state
            2) and create2 contract is not in the state
        b) on a different tx, attempt to recreate the contract
    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then in a different tx, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract
        b) on a different tx, attempt to recreate the contract
    Verify that the test case described
    in https://wiki.hyperledger.org/pages/viewpage.action?pageId=117440824 is covered
    """
    assert call_create2_contract_in_between or call_create2_contract_at_the_end, "invalid test"

    # Storage locations
    create2_constructor_worked = 1
    first_create2_result = 2
    second_create2_result = 3
    code_worked = 4

    # Values
    first_create2_value = 10
    first_call_value = 100
    second_create2_value = 1000
    second_call_value = 10000

    # Call addresses
    address_zero = Address(0x00)
    call_address_in_between = (
        selfdestruct_contract_address if call_create2_contract_in_between else address_zero
    )
    call_address_in_the_end = (
        selfdestruct_contract_address if call_create2_contract_at_the_end else address_zero
    )

    # Executor contract address
    executor_contract_code = (
        Op.JUMPDEST()
        # Make a subcall that do CREATE2 and returns its the result
        + Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.CALL(
            100000, deployer_contract_address, first_create2_value, 0, Op.CALLDATASIZE(), 0, 32
        )
        + Op.SSTORE(
            first_create2_result,
            Op.MLOAD(0),
        )
        # In case the create2 didn't work, flush account balance
        + Op.CALL(100000, deployer_contract_address, 0, 0, 0, 0, 0)
        # Call to the created account to trigger selfdestruct
        + Op.CALL(100000, call_address_in_between, first_call_value, 0, 0, 0, 0)
        # Make a subcall that do CREATE2 collision and returns its address as the result
        + Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.CALL(
            100000, deployer_contract_address, second_create2_value, 0, Op.CALLDATASIZE(), 0, 32
        )
        + Op.SSTORE(
            second_create2_result,
            Op.MLOAD(0),
        )
        # Call to the created account to trigger selfdestruct
        + Op.CALL(100000, call_address_in_the_end, second_call_value, 0, 0, 0, 0)
        + Op.SSTORE(code_worked, 1)
    )
    executor_contract_init_balance = 100_000
    executor_contract_init_storage:\
        Dict[Union[str, int, bytes, SupportsBytes], Union[str, int, bytes, SupportsBytes]] =\
        {
            first_create2_result: 0xFF,
            second_create2_result: 0xFF
        }
    executor_contract_address = pre.deploy_contract(
        executor_contract_code,
        balance=executor_contract_init_balance,
        storage=executor_contract_init_storage,
    )

    # Post state
    post: Dict[Address, Union[Account, object]] = {}

    # Create2 address only exists if it was pre-existing and after cancun
    post[selfdestruct_contract_address] = (
        Account(
            balance=0,
            nonce=1,
            code=selfdestruct_contract_bytecode,
            storage={create2_constructor_worked: 0x00},
        )
        if create2_dest_already_in_state and fork >= Cancun
        else Account.NONEXISTENT
    )

    # Create2 initcode is only executed if the contract did not already exist
    post[create2_storage_contract_address] = Account(
        storage={create2_constructor_worked: int(not create2_dest_already_in_state)}
    )

    # Entry code that makes the calls to the create2 contract creator
    post[executor_contract_address] = Account(
        storage={
            code_worked: 0x01,
            # First create2 only works if the contract was not preexisting
            first_create2_result: 0x00
            if create2_dest_already_in_state
            else selfdestruct_contract_address,
            # Second create2 must never work
            second_create2_result: 0x00,
        }
    )

    # Calculate the destination account expected balance for the selfdestruct/sendall calls
    sendall_destination_balance = (
        selfdestruct_contract_init_balance
        if create2_dest_already_in_state
        else first_create2_value
    )

    if call_create2_contract_in_between:
        sendall_destination_balance += first_call_value

    if call_create2_contract_at_the_end:
        sendall_destination_balance += second_call_value

    post[selfdestruct_recipient_address] = Account(balance=sendall_destination_balance)

    tx = Transaction(
        sender=sender,
        to=executor_contract_address,
        data=selfdestruct_contract_initcode,
        gas_limit=tx_gas_limit,
        value=0,
    )

    state_test(env=env, pre=pre, post=post, tx=tx)


@pytest.mark.valid_from("Paris")
@pytest.mark.parametrize(
    "create2_dest_already_in_state",
    (True, False),
)
@pytest.mark.parametrize(
    "call_create2_contract_at_the_end",
    (True, False),
)
def test_dynamic_create2_selfdestruct_collision_two_different_transactions(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    env: Environment,
    fork: Fork,
    sender: EOA,
    create2_dest_already_in_state: bool,
    call_create2_contract_at_the_end: bool,
    selfdestruct_contract_address: Address,
    selfdestruct_contract_bytecode: Bytecode,
    selfdestruct_contract_init_balance: int,
    selfdestruct_contract_initcode: Initcode,
    deployer_contract_address: Address,
    create2_storage_contract_address: Address,
    selfdestruct_recipient_address: Address,
    tx_gas_limit: int,
):
    """
    Dynamic Create2->Suicide->Create2 collision scenario.

    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then on a different call, in the same tx, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract
            1) and create2 contract already in the state
            2) and create2 contract is not in the state
        b) on a different tx, attempt to recreate the contract <=== Covered in this test
    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then in a different tx, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract
        b) on a different tx, attempt to recreate the contract
    Verify that the test case described
    in https://wiki.hyperledger.org/pages/viewpage.action?pageId=117440824 is covered
    """
    # Storage locations
    create2_constructor_worked = 1
    first_create2_result = 2
    second_create2_result = 3
    code_worked = 4

    # Call addresses
    address_zero = Address(0x00)
    call_address_in_the_end = (
        selfdestruct_contract_address if call_create2_contract_at_the_end else address_zero
    )

    # Values
    first_create2_value = 10
    first_call_value = 100
    second_create2_value = 1000
    second_call_value = 10000

    # Executor contracts
    executor_contract_first_code = (
        Op.JUMPDEST()
        # Make a subcall that do CREATE2 and returns its the result
        + Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.CALL(
            100000, deployer_contract_address, first_create2_value, 0, Op.CALLDATASIZE(), 0, 32
        )
        + Op.SSTORE(
            first_create2_result,
            Op.MLOAD(0),
        )
        # In case the create2 didn't work, flush account balance
        + Op.CALL(100000, deployer_contract_address, 0, 0, 0, 0, 0)
        # Call to the created account to trigger selfdestruct
        + Op.CALL(100000, selfdestruct_contract_address, first_call_value, 0, 0, 0, 0)
        + Op.SSTORE(code_worked, 1)
    )
    executor_contract_first_init_balance = 100_000
    executor_contract_first_init_storage:\
        Dict[Union[str, int, bytes, SupportsBytes], Union[str, int, bytes, SupportsBytes]] = \
        {
            first_create2_result: 0xFF
        }

    executor_contract_first_address = pre.deploy_contract(
        executor_contract_first_code,
        balance=executor_contract_first_init_balance,
        storage=executor_contract_first_init_storage,
    )

    executor_contract_second_code = (
        Op.JUMPDEST()
        # Make a subcall that do CREATE2 collision and returns its address as the result
        + Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.CALL(
            100000, deployer_contract_address, second_create2_value, 0, Op.CALLDATASIZE(), 0, 32
        )
        + Op.SSTORE(
            second_create2_result,
            Op.MLOAD(0),
        )
        # Call to the created account to trigger selfdestruct
        + Op.CALL(200000, call_address_in_the_end, second_call_value, 0, 0, 0, 0)
        + Op.SSTORE(code_worked, 1)
    )
    executor_contract_second_init_balance = 100_000
    executor_contract_second_init_storage:\
        Dict[Union[str, int, bytes, SupportsBytes], Union[str, int, bytes, SupportsBytes]] =\
        {
            second_create2_result: 0xFF
        }
    executor_contract_second_address = pre.deploy_contract(
        executor_contract_second_code,
        balance=executor_contract_second_init_balance,
        storage=executor_contract_second_init_storage,
    )

    # Post state
    post: Dict[Address, Union[Account, object]] = {}

    # Create2 address only exists if it was pre-existing and after cancun
    post[selfdestruct_contract_address] = (
        Account(
            balance=0,
            nonce=1,
            code=selfdestruct_contract_bytecode,
            storage={create2_constructor_worked: 0x00},
        )
        if create2_dest_already_in_state and fork >= Cancun
        else (
            Account.NONEXISTENT
            if call_create2_contract_at_the_end
            else Account(
                balance=second_create2_value, nonce=1, code=selfdestruct_contract_bytecode
            )
        )
    )

    # after Cancun Create2 initcode is only executed if the contract did not already exist
    # and before it will always be executed as the first tx deletes the account
    post[create2_storage_contract_address] = Account(
        storage={
            create2_constructor_worked: int(fork < Cancun or not create2_dest_already_in_state)
        }
    )

    # Entry code that makes the calls to the create2 contract creator
    post[executor_contract_first_address] = Account(
        storage={
            code_worked: 0x01,
            # First create2 only works if the contract was not preexisting
            first_create2_result: 0x00
            if create2_dest_already_in_state
            else selfdestruct_contract_address,
        }
    )
    post[executor_contract_second_address] = Account(
        storage={
            code_worked: 0x01,
            # Second create2 will not collide before Cancun as the first tx calls selfdestruct
            # After cancun it will collide only if create2_dest_already_in_state otherwise the
            # first tx creates and deletes it
            second_create2_result: (
                (0x00 if create2_dest_already_in_state else selfdestruct_contract_address)
                if fork >= Cancun
                else selfdestruct_contract_address
            ),
        }
    )

    # Calculate the destination account expected balance for the selfdestruct/sendall calls
    sendall_destination_balance = 0

    if create2_dest_already_in_state:
        sendall_destination_balance += selfdestruct_contract_init_balance
        if fork >= Cancun:
            # first create2 fails, but first calls ok. the account is not removed on cancun
            # therefore with the second create2 it is not successful
            sendall_destination_balance += first_call_value
        else:
            # first create2 fails, first calls totally removes the account
            # in the second transaction second create2 is successful
            sendall_destination_balance += first_call_value
            if call_create2_contract_at_the_end:
                sendall_destination_balance += second_create2_value
    else:
        # if no account in the state, first create2 successful, first call successful and removes
        # because it is removed in the next transaction second create2 successful
        sendall_destination_balance = first_create2_value + first_call_value
        if call_create2_contract_at_the_end:
            sendall_destination_balance += second_create2_value

    if call_create2_contract_at_the_end:
        sendall_destination_balance += second_call_value

    post[selfdestruct_recipient_address] = Account(balance=sendall_destination_balance)

    blockchain_test(
        genesis_environment=env,
        pre=pre,
        post=post,
        blocks=[
            Block(
                txs=[
                    Transaction(
                        sender=sender,
                        to=executor_contract_first_address,
                        data=selfdestruct_contract_initcode,
                        gas_limit=tx_gas_limit,
                        value=0,
                    ),
                    Transaction(
                        sender=sender,
                        to=executor_contract_second_address,
                        data=selfdestruct_contract_initcode,
                        gas_limit=tx_gas_limit,
                        value=0,
                    ),
                ]
            )
        ],
    )


@pytest.mark.valid_from("Paris")
@pytest.mark.parametrize(
    "selfdestruct_on_first_tx,recreate_on_first_tx",
    [
        (False, False),
        (True, False),
        (True, True),
    ],
)
def test_dynamic_create2_selfdestruct_collision_multi_tx(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    fork: Fork,
    sender: EOA,
    selfdestruct_on_first_tx: bool,
    recreate_on_first_tx: bool,
    selfdestruct_contract_bytecode: Bytecode,
    selfdestruct_contract_initcode: Initcode,
    deployer_contract_address: Address,
    create2_storage_contract_address: Address,
    selfdestruct_recipient_address: Address,
    tx_gas_limit: int,
    create2_salt: int,
):
    """
    Dynamic Create2->Suicide->Create2 collision scenario over multiple transactions.

    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then on a different call, in the same or different tx but same block, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract
        b) on a different tx, attempt to recreate the contract
    Perform a CREATE2, make sure that the initcode sets at least a couple of storage keys,
    then in a different tx, perform a self-destruct.
    Then:
        a) on the same tx, attempt to recreate the contract       <=== Covered in this test
        b) on a different tx, attempt to recreate the contract    <=== Covered in this test
    Verify that the test case described
    in https://wiki.hyperledger.org/pages/viewpage.action?pageId=117440824 is covered
    """
    if recreate_on_first_tx:
        assert selfdestruct_on_first_tx, "invalid test"

    # Storage locations
    create2_constructor_worked = 1
    first_create2_result = 2
    second_create2_result = 3
    part_1_worked = 4
    part_2_worked = 5

    # Values
    first_create2_value = 3
    first_call_value = 5
    second_create2_value = 7
    second_call_value = 11

    # Call address
    selfdestruct_contract_address = compute_create2_address(
        deployer_contract_address, create2_salt, selfdestruct_contract_initcode
    )

    # Code is divided in two transactions part of the same block
    first_tx_code = Bytecode()
    second_tx_code = Bytecode()

    first_tx_code += (
        Op.JUMPDEST()
        # Make a subcall that do CREATE2 and returns its the result
        + Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
        + Op.CALL(
            100000, deployer_contract_address, first_create2_value, 0, Op.CALLDATASIZE(), 0, 32
        )
        + Op.SSTORE(
            first_create2_result,
            Op.MLOAD(0),
        )
    )

    if selfdestruct_on_first_tx:
        first_tx_code += (
            # Call to the created account to trigger selfdestruct
            Op.CALL(100000, selfdestruct_contract_address, first_call_value, 0, 0, 0, 0)
        )
    else:
        second_tx_code += (
            # Call to the created account to trigger selfdestruct
            Op.CALL(100000, selfdestruct_contract_address, first_call_value, 0, 0, 0, 0)
        )

    if recreate_on_first_tx:
        first_tx_code += (
            # Make a subcall that do CREATE2 collision and returns its address as the result
            Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
            + Op.CALL(
                100000,
                deployer_contract_address,
                second_create2_value,
                0,
                Op.CALLDATASIZE(),
                0,
                32,
            )
            + Op.SSTORE(
                second_create2_result,
                Op.MLOAD(0),
            )
        )

    else:
        second_tx_code += (
            # Make a subcall that do CREATE2 collision and returns its address as the result
            Op.CALLDATACOPY(0, 0, Op.CALLDATASIZE())
            + Op.CALL(
                100000,
                deployer_contract_address,
                second_create2_value,
                0,
                Op.CALLDATASIZE(),
                0,
                32,
            )
            + Op.SSTORE(
                second_create2_result,
                Op.MLOAD(0),
            )
        )

    # Second tx code always calls the create2 contract at the end
    second_tx_code += Op.CALL(100000, selfdestruct_contract_address, second_call_value, 0, 0, 0, 0)

    first_tx_code += Op.SSTORE(part_1_worked, 1)
    second_tx_code += Op.SSTORE(part_2_worked, 1)

    # Executor contract
    executor_contract_code = Conditional(
        # Depending on the tx, execute the first or second tx code
        condition=Op.EQ(Op.SLOAD(part_1_worked), 0),
        if_true=first_tx_code,
        if_false=second_tx_code,
    )
    executor_contract_init_balance = 100_000

    executor_contract_init_storage:\
        Dict[Union[str, int, bytes, SupportsBytes], Union[str, int, bytes, SupportsBytes]] = \
        {
            first_create2_result: 0xFF,
            second_create2_result: 0xFF,
        }
    executor_contract_address = pre.deploy_contract(
        executor_contract_code,
        balance=executor_contract_init_balance,
        storage=executor_contract_init_storage,
    )

    # Post state
    post: Dict[Address, Union[Account, object]] = {}

    # Create2 address only exists if it was pre-existing and after cancun
    account_will_exist_with_code = not selfdestruct_on_first_tx and fork >= Cancun
    # If the contract is self-destructed and we also attempt to recreate it on the first tx,
    # the second call on the second tx will only place balance in the account
    account_will_exist_with_balance = selfdestruct_on_first_tx and recreate_on_first_tx

    post[selfdestruct_contract_address] = (
        Account(
            balance=0,
            nonce=1,
            code=selfdestruct_contract_bytecode,
            storage={create2_constructor_worked: 0x01},
        )
        if account_will_exist_with_code
        else (
            Account(balance=second_call_value, nonce=0)
            if account_will_exist_with_balance
            else Account.NONEXISTENT
        )
    )

    # Create2 initcode saves storage unconditionally
    post[create2_storage_contract_address] = Account(storage={create2_constructor_worked: 0x01})

    # Entry code that makes the calls to the create2 contract creator
    post[executor_contract_address] = Account(
        storage={
            part_1_worked: 0x01,
            part_2_worked: 0x01,
            # First create2 always works
            first_create2_result: selfdestruct_contract_address,
            # Second create2 only works if we successfully self-destructed on the first tx
            second_create2_result: (
                selfdestruct_contract_address
                if selfdestruct_on_first_tx and not recreate_on_first_tx
                else 0x00
            ),
        }
    )

    # Calculate the destination account expected balance for the selfdestruct/sendall calls
    sendall_destination_balance = first_create2_value + first_call_value

    if not account_will_exist_with_balance:
        sendall_destination_balance += second_call_value

    if selfdestruct_on_first_tx and not recreate_on_first_tx:
        sendall_destination_balance += second_create2_value

    post[selfdestruct_recipient_address] = Account(balance=sendall_destination_balance)

    blockchain_test(
        genesis_environment=Environment(),
        pre=pre,
        post=post,
        blocks=[
            Block(
                txs=[
                    Transaction(
                        sender=sender,
                        to=executor_contract_address,
                        data=selfdestruct_contract_initcode,
                        gas_limit=tx_gas_limit,
                        value=0,
                    ),
                    Transaction(
                        sender=sender,
                        to=executor_contract_address,
                        data=selfdestruct_contract_initcode,
                        gas_limit=tx_gas_limit,
                        value=0,
                    ),
                ]
            )
        ],
    )
