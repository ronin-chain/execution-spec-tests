"""Defines EIP-7623 specification constants and functions."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

from ethereum_test_tools import Transaction


@dataclass(frozen=True)
class ReferenceSpec:
    """Defines the reference spec version and git path."""

    git_path: str
    version: str


ref_spec_7623 = ReferenceSpec("EIPS/eip-7623.md", "9104d079c04737b1fec5f7150715f024d8028558")


# Constants
@dataclass(frozen=True)
class Spec:
    """
    Parameters from the EIP-7623 specifications as defined at
    https://eips.ethereum.org/EIPS/eip-7623.
    """

    STANDARD_TOKEN_COST = 4
    TOTAL_COST_FLOOR_PER_TOKEN = 10

    BLOB_TX_TYPE = 0x03
    FIELD_ELEMENTS_PER_BLOB = 4096
    BLS_MODULUS = 0x73EDA753299D7D483339D80809A1D80553BDA402FFFE5BFEFFFFFFFF00000001
    BLOB_COMMITMENT_VERSION_KZG = 1
    POINT_EVALUATION_PRECOMPILE_ADDRESS = 10
    POINT_EVALUATION_PRECOMPILE_GAS = 50_000
    # MAX_VERSIONED_HASHES_LIST_SIZE = 2**24
    # MAX_CALLDATA_SIZE = 2**24
    # MAX_ACCESS_LIST_SIZE = 2**24
    # MAX_ACCESS_LIST_STORAGE_KEYS = 2**24
    # MAX_TX_WRAP_COMMITMENTS = 2**12
    # LIMIT_BLOBS_PER_TX = 2**12
    HASH_OPCODE_BYTE = 0x49
    HASH_GAS_COST = 3
    INF_POINT = (0xC0 << 376).to_bytes(48, byteorder="big")

    @classmethod
    def kzg_to_versioned_hash(
        cls,
        kzg_commitment: bytes | int,  # 48 bytes
        blob_commitment_version_kzg: Optional[bytes | int] = None,
    ) -> bytes:
        """Calculate versioned hash for a given KZG commitment."""
        if blob_commitment_version_kzg is None:
            blob_commitment_version_kzg = cls.BLOB_COMMITMENT_VERSION_KZG
        if isinstance(kzg_commitment, int):
            kzg_commitment = kzg_commitment.to_bytes(48, "big")
        if isinstance(blob_commitment_version_kzg, int):
            blob_commitment_version_kzg = blob_commitment_version_kzg.to_bytes(1, "big")
        return blob_commitment_version_kzg + sha256(kzg_commitment).digest()[1:]

    @classmethod
    def get_total_blob_gas(cls, *, tx: Transaction, blob_gas_per_blob: int) -> int:
        """Calculate the total blob gas for a transaction."""
        if tx.blob_versioned_hashes is None:
            return 0
        return blob_gas_per_blob * len(tx.blob_versioned_hashes)
