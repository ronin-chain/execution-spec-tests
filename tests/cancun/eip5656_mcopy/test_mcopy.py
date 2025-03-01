"""
abstract: Tests [EIP-5656: MCOPY - Memory copying instruction](https://eips.ethereum.org/EIPS/eip-5656)
    Test copy operations of [EIP-5656: MCOPY - Memory copying instruction](https://eips.ethereum.org/EIPS/eip-5656).

"""  # noqa: E501

from typing import Mapping

import pytest

from ethereum_test_tools import (
    Account,
    Address,
    Alloc,
    Bytecode,
    Environment,
    Hash,
    StateTestFiller,
    Storage,
    Transaction,
    ceiling_division,
    keccak256,
)
from ethereum_test_tools import Opcodes as Op

from .common import REFERENCE_SPEC_GIT_PATH, REFERENCE_SPEC_VERSION, mcopy

REFERENCE_SPEC_GIT_PATH = REFERENCE_SPEC_GIT_PATH
REFERENCE_SPEC_VERSION = REFERENCE_SPEC_VERSION


@pytest.fixture
def initial_memory() -> bytes:
    """Init memory for the test."""
    return bytes(range(0x00, 0x100))


@pytest.fixture
def final_memory(*, dest: int, src: int, length: int, initial_memory: bytes) -> bytes:
    """Memory after the MCOPY operation."""
    return mcopy(dest=dest, src=src, length=length, memory=initial_memory)


@pytest.fixture
def code_storage() -> Storage:
    """Storage for the code contract."""
    return Storage()


@pytest.fixture
def code_bytecode(
    initial_memory: bytes,
    final_memory: bytes,
    code_storage: Storage,
) -> Bytecode:
    """
    Prepare bytecode and storage for the test, based on the starting memory and the final
    memory that resulted from the copy.
    """
    bytecode = Bytecode()

    # Fill memory with initial values
    for i in range(0, len(initial_memory), 0x20):
        bytecode += Op.MSTORE(i, Op.PUSH32(initial_memory[i : i + 0x20]))

    # Perform the MCOPY according to calldata values
    bytecode += Op.MCOPY(
        Op.CALLDATALOAD(0x00),
        Op.CALLDATALOAD(0x20),
        Op.CALLDATALOAD(0x40),
    )

    final_byte_length = ceiling_division(len(final_memory), 0x20) * 0x20
    # First save msize
    bytecode += Op.SSTORE(
        code_storage.store_next(final_byte_length),
        Op.MSIZE,
    )

    # Then save the hash of the entire memory
    bytecode += Op.SSTORE(
        code_storage.store_next(keccak256(final_memory.ljust(final_byte_length, b"\x00"))),
        Op.SHA3(0, Op.MSIZE),
    )

    # Store all memory in the initial range to verify the MCOPY
    for w in range(0, len(initial_memory) // 0x20):
        bytecode += Op.SSTORE(
            code_storage.store_next(final_memory[w * 0x20 : w * 0x20 + 0x20]),
            Op.MLOAD(w * 0x20),
        )

    # If the memory was extended beyond the initial range, store the last word of the resulting
    # memory into storage too
    if len(final_memory) > len(initial_memory):
        last_word = ceiling_division(len(final_memory), 0x20) - 1
        bytecode += Op.SSTORE(
            code_storage.store_next(
                final_memory[last_word * 0x20 : (last_word + 1) * 0x20].ljust(32, b"\x00")
            ),
            Op.MLOAD(last_word * 0x20),
        )

    return bytecode


@pytest.fixture
def code_address(pre: Alloc, code_bytecode: Bytecode) -> Address:
    """Address of the contract that is going to perform the MCOPY operation."""
    return pre.deploy_contract(code_bytecode)


@pytest.fixture
def tx_gas_limit() -> int:  # noqa: D103
    return 3_000_000


@pytest.fixture
def tx(  # noqa: D103
    pre: Alloc, code_address: Address, dest: int, src: int, length: int, tx_gas_limit: int
) -> Transaction:
    return Transaction(
        sender=pre.fund_eoa(),
        to=code_address,
        data=Hash(dest) + Hash(src) + Hash(length),
        gas_limit=tx_gas_limit,
    )


@pytest.fixture
def post(code_address: Address, code_storage: Storage) -> Mapping:  # noqa: D103
    return {
        code_address: Account(storage=code_storage),
    }


@pytest.mark.parametrize(
    "dest,src,length",
    [
        (0x00, 0x00, 0x00),
        (2**256 - 1, 0x00, 0x00),
        (0x00, 0x00, 0x01),
        (0x00, 0x00, 0x20),
        (0x01, 0x00, 0x01),
        (0x01, 0x00, 0x20),
        (0x11, 0x11, 0x01),
        (0x11, 0x11, 0x20),
        (0x11, 0x11, 0x40),
        (0x10, 0x00, 0x40),
        (0x00, 0x10, 0x40),
        (0x0F, 0x10, 0x40),
        (0x100, 0x01, 0x01),
        (0x100, 0x01, 0x20),
        (0x100, 0x01, 0x1F),
        (0x100, 0x01, 0x21),
        (0x00, 0x00, 0x100),
        (0x100, 0x00, 0x100),
        (0x200, 0x00, 0x100),
        (0x00, 0x100, 0x100),
        (0x100, 0x100, 0x01),
    ],
    ids=[
        "zero_inputs",
        "zero_length_out_of_bounds_destination",
        "single_byte_rewrite",
        "full_word_rewrite",
        "single_byte_forward_overwrite",
        "full_word_forward_overwrite",
        "mid_word_single_byte_rewrite",
        "mid_word_single_word_rewrite",
        "mid_word_multi_word_rewrite",
        "two_words_forward_overwrite",
        "two_words_backward_overwrite",
        "two_words_backward_overwrite_single_byte_offset",
        "single_byte_memory_extension",
        "single_word_memory_extension",
        "single_word_minus_one_byte_memory_extension",
        "single_word_plus_one_byte_memory_extension",
        "full_memory_rewrite",
        "full_memory_copy",
        "full_memory_copy_offset",
        "full_memory_clean",
        "out_of_bounds_memory_extension",
    ],
)
@pytest.mark.with_all_evm_code_types
@pytest.mark.valid_from("Cancun")
def test_valid_mcopy_operations(
    state_test: StateTestFiller,
    pre: Alloc,
    post: Mapping[str, Account],
    tx: Transaction,
):
    """
    Perform MCOPY operations using different offsets and lengths:
      - Zero inputs
      - Memory rewrites (copy from and to the same location)
      - Memory overwrites (copy from and to different locations)
      - Memory extensions (copy to a location that is out of bounds)
      - Memory clear (copy from a location that is out of bounds).
    """
    state_test(
        env=Environment(),
        pre=pre,
        post=post,
        tx=tx,
    )


@pytest.mark.parametrize("dest", [0x00, 0x20])
@pytest.mark.parametrize("src", [0x00, 0x20])
@pytest.mark.parametrize("length", [0x00, 0x01])
@pytest.mark.parametrize("initial_memory", [bytes()], ids=["empty_memory"])
@pytest.mark.with_all_evm_code_types
@pytest.mark.valid_from("Cancun")
def test_mcopy_on_empty_memory(
    state_test: StateTestFiller,
    pre: Alloc,
    post: Mapping[str, Account],
    tx: Transaction,
):
    """Perform MCOPY operations on an empty memory, using different offsets and lengths."""
    state_test(
        env=Environment(),
        pre=pre,
        post=post,
        tx=tx,
    )
