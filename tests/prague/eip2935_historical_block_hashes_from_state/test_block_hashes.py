"""
abstract: Tests [EIP-2935: Serve historical block hashes from state](https://eips.ethereum.org/EIPS/eip-2935)
    Test [EIP-2935: Serve historical block hashes from state](https://eips.ethereum.org/EIPS/eip-2935).
"""  # noqa: E501

from typing import Dict, List

import pytest

from ethereum_test_tools import (
    Account,
    Address,
    Alloc,
    Block,
    BlockchainTestFiller,
    Bytecode,
    Storage,
    Transaction,
)
from ethereum_test_tools import Opcodes as Op

from .spec import Spec, ref_spec_2935

REFERENCE_SPEC_GIT_PATH = ref_spec_2935.git_path
REFERENCE_SPEC_VERSION = ref_spec_2935.version


def generate_block_check_code(
    sub_block_number: int,
    storage: Storage,
    check_contract_first: bool = False,
) -> Bytecode:
    """
    Generate EVM code to check that the block hashes are correctly stored in the state.

    Args:
        sub_block_number (int): The number of blocks to check back from the current block.
        storage (Storage): The storage object to use.
        check_contract_first (bool): Whether to check the contract first, for slot warming checks.

    """
    populated_blockhash = sub_block_number <= Spec.BLOCKHASH_OLD_WINDOW
    populated_history_storage_contract = sub_block_number <= Spec.HISTORY_SERVE_WINDOW

    blockhash_key = storage.store_next(not populated_blockhash)
    contract_key = storage.store_next(not populated_history_storage_contract)

    check_blockhash = Op.SSTORE(
        blockhash_key, Op.ISZERO(Op.BLOCKHASH(Op.SUB(Op.NUMBER(), sub_block_number)))
    )
    check_contract = (
        Op.MSTORE(0, Op.SUB(Op.NUMBER(), sub_block_number))
        + Op.POP(Op.CALL(Op.GAS, Spec.HISTORY_STORAGE_ADDRESS, 0, 0, 32, 32, 32))
        + Op.SSTORE(contract_key, Op.ISZERO(Op.MLOAD(32)))
    )

    if check_contract_first:
        code = check_contract + check_blockhash
    else:
        code = check_blockhash + check_contract

    if populated_history_storage_contract and populated_blockhash:
        # Both values must be equal
        store_equal_key = storage.store_next(True)
        code += Op.SSTORE(
            store_equal_key,
            Op.EQ(Op.MLOAD(32), Op.BLOCKHASH(Op.SUB(Op.NUMBER(), sub_block_number))),
        )

    code += Op.MSTORE(32, 0)

    return code


@pytest.mark.parametrize(
    "block_count,check_contract_first",
    [
        pytest.param(32, False, id="check_blockhash_first"),
        pytest.param(32, True, id="check_contract_first"),
    ],
)
@pytest.mark.valid_from("Prague")
def test_block_hashes_history_sequence(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    block_count: int,
    check_contract_first: bool,
):
    """
    Tests that block hashes are stored correctly at the system contract address after the fork
    transition. Block hashes are stored incrementally at the transition until the
    `HISTORY_SERVE_WINDOW` ring buffer is full. Afterwards the oldest block hash is replaced by the
    new one.
    """
    blocks: List[Block] = []

    for _ in range(block_count):
        # Generate empty blocks after the fork.
        blocks.append(Block())

    sender = pre.fund_eoa()
    post: Dict[Address, Account] = {}

    txs = []
    # On these blocks, `BLOCKHASH` will still return values for the last 256 blocks, and
    # `HISTORY_STORAGE_ADDRESS` should now serve values for the previous blocks in the new
    # fork.
    code = Bytecode()
    storage = Storage()

    for i in range(block_count):
        code += generate_block_check_code(
            sub_block_number=i + 1,
            storage=storage,
            check_contract_first=check_contract_first,
        )

    check_blocks_after_fork_address = pre.deploy_contract(code)
    txs.append(
        Transaction(
            to=check_blocks_after_fork_address,
            gas_limit=1_000_000,
            sender=sender,
        )
    )
    post[check_blocks_after_fork_address] = Account(storage=storage)

    blocks.append(Block(txs=txs))

    blockchain_test(
        pre=pre,
        blocks=blocks,
        post=post,
    )


@pytest.mark.parametrize(
    "check_contract_first",
    [
        pytest.param(False, id="check_blockhash_first"),
        pytest.param(True, id="check_contract_first"),
    ],
)
@pytest.mark.valid_from("Prague")
@pytest.mark.fill(pytest.mark.skip(reason="execute-only test, fill requires high resource"))
def test_block_hashes_history(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    check_contract_first: bool,
):
    """
    Tests that block hashes are stored correctly at the system contract address after the fork
    transition. Block hashes are stored incrementally at the transition until the
    `HISTORY_SERVE_WINDOW` ring buffer is full. Afterwards the oldest block hash is replaced by the
    new one.
    """
    blocks: List[Block] = []

    sender = pre.fund_eoa()
    post: Dict[Address, Account] = {}

    txs = []
    # On these blocks, `BLOCKHASH` will still return values for the last 256 blocks, and
    # `HISTORY_STORAGE_ADDRESS` should now serve values for the previous blocks in the new
    # fork.
    code = Bytecode()
    storage = Storage()

    for _ in range(Spec.HISTORY_SERVE_WINDOW):
        # Generate empty blocks after the fork.
        blocks.append(Block())

    # Check the first block outside of the window if any
    code += generate_block_check_code(
        sub_block_number=Spec.HISTORY_SERVE_WINDOW + 1,
        storage=storage,
        check_contract_first=check_contract_first,
    )

    # Check the first block inside the window
    code += generate_block_check_code(
        sub_block_number=Spec.HISTORY_SERVE_WINDOW,
        storage=storage,
        check_contract_first=check_contract_first,
    )

    # Check the first block outside the BLOCKHASH window
    code += generate_block_check_code(
        sub_block_number=Spec.BLOCKHASH_OLD_WINDOW + 1,
        storage=storage,
        check_contract_first=check_contract_first,
    )

    # Check the first block inside the BLOCKHASH window
    code += generate_block_check_code(
        sub_block_number=Spec.BLOCKHASH_OLD_WINDOW,
        storage=storage,
        check_contract_first=check_contract_first,
    )

    # Check the previous block
    code += generate_block_check_code(
        sub_block_number=1,
        storage=storage,
        check_contract_first=check_contract_first,
    )

    check_blocks_after_fork_address = pre.deploy_contract(code)
    txs.append(
        Transaction(
            to=check_blocks_after_fork_address,
            gas_limit=1_000_000,
            sender=sender,
        )
    )
    post[check_blocks_after_fork_address] = Account(storage=storage)

    blocks.append(Block(txs=txs))

    blockchain_test(
        pre=pre,
        blocks=blocks,
        post=post,
    )


@pytest.mark.parametrize(
    "block_number,reverts",
    [
        pytest.param(1, True, id="current_block"),
        pytest.param(2, True, id="future_block"),
        pytest.param(2**64 - 1, True, id="2**64-1"),
        pytest.param(2**64, True, id="2**64"),
    ],
)
@pytest.mark.valid_from("Prague")
def test_invalid_history_contract_calls(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    block_number: int,
    reverts: bool,
):
    """
    Test calling the history contract with invalid block numbers, such as blocks from the future
    or overflowing block numbers.

    Also test the BLOCKHASH opcode with the same block numbers, which should not affect the
    behavior of the opcode, even after verkle.
    """
    storage = Storage()

    return_code_slot = storage.store_next(not reverts)
    returned_block_hash_slot = storage.store_next(0)
    block_hash_opcode_slot = storage.store_next(0)

    return_offset = 64
    return_size = 32
    args_size = 32

    # Check the first block outside of the window if any
    if block_number == 1:
        code = (
            Op.MSTORE(0, Op.NUMBER())
            + Op.SSTORE(
                return_code_slot,
                Op.CALL(
                    address=Spec.HISTORY_STORAGE_ADDRESS,
                    args_offset=0,
                    args_size=args_size,
                    ret_offset=return_offset,
                    ret_size=return_size,
                ),
            )
            + Op.SSTORE(returned_block_hash_slot, Op.MLOAD(return_offset))
            + Op.SSTORE(block_hash_opcode_slot, Op.BLOCKHASH(block_number))
        )
    elif block_number == 2:
        code = (
            Op.MSTORE(0, Op.ADD(Op.NUMBER(), 1))
            + Op.SSTORE(
                return_code_slot,
                Op.CALL(
                    address=Spec.HISTORY_STORAGE_ADDRESS,
                    args_offset=0,
                    args_size=args_size,
                    ret_offset=return_offset,
                    ret_size=return_size,
                ),
            )
            + Op.SSTORE(returned_block_hash_slot, Op.MLOAD(return_offset))
            + Op.SSTORE(block_hash_opcode_slot, Op.BLOCKHASH(block_number))
        )
    else:
        code = (
            Op.MSTORE(0, block_number)
            + Op.SSTORE(
                return_code_slot,
                Op.CALL(
                    address=Spec.HISTORY_STORAGE_ADDRESS,
                    args_offset=0,
                    args_size=args_size,
                    ret_offset=return_offset,
                    ret_size=return_size,
                ),
            )
            + Op.SSTORE(returned_block_hash_slot, Op.MLOAD(return_offset))
            + Op.SSTORE(block_hash_opcode_slot, Op.BLOCKHASH(block_number))
        )
    check_contract_address = pre.deploy_contract(code, storage=storage.canary())

    txs = [
        Transaction(
            to=check_contract_address,
            gas_limit=1_000_000,
            sender=pre.fund_eoa(),
        )
    ]
    post = {check_contract_address: Account(storage=storage)}

    blocks = [Block(txs=txs)]
    blockchain_test(
        pre=pre,
        blocks=blocks,
        post=post,
        reverts=reverts,
    )


@pytest.mark.parametrize(
    "args_size,reverts",
    [
        pytest.param(0, True, id="zero_size"),
        pytest.param(33, True, id="too_large"),
        pytest.param(31, True, id="too_small"),
    ],
)
@pytest.mark.valid_from("Prague")
def test_invalid_history_contract_calls_input_size(
    blockchain_test: BlockchainTestFiller,
    pre: Alloc,
    reverts: bool,
    args_size: int,
):
    """Test calling the history contract with invalid input sizes."""
    storage = Storage()

    return_code_slot = storage.store_next(not reverts, "history storage call result")
    returned_block_hash_slot = storage.store_next(0)

    return_offset = 64
    return_size = 32
    block_number = 0

    # Check the first block outside of the window if any
    code = (
        Op.MSTORE(0, block_number)
        + Op.SSTORE(
            return_code_slot,
            Op.CALL(
                address=Spec.HISTORY_STORAGE_ADDRESS,
                args_offset=0,
                args_size=args_size,
                ret_offset=return_offset,
                ret_size=return_size,
            ),
        )
        + Op.SSTORE(returned_block_hash_slot, Op.MLOAD(return_offset))
    )
    check_contract_address = pre.deploy_contract(code, storage=storage.canary())

    txs = [
        Transaction(
            to=check_contract_address,
            gas_limit=1_000_000,
            sender=pre.fund_eoa(),
        )
    ]
    post = {check_contract_address: Account(storage=storage)}

    blocks = [Block(txs=txs)]
    blockchain_test(
        pre=pre,
        blocks=blocks,
        post=post,
        reverts=reverts,
    )
