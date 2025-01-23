"""Helper functions/classes used to generate Ethereum tests."""

import os
import struct
from dataclasses import MISSING, dataclass, fields
from typing import List, SupportsBytes

import ckzg
from ethereum.rlp import encode

from ethereum_test_base_types.base_types import Address, Bytes, Hash
from ethereum_test_base_types.conversions import BytesConvertible, FixedSizeBytesConvertible
from ethereum_test_vm import Opcodes as Op
from .types import EOA, int_to_bytes

# Blob constants
BLOB_FIELD_SIZE = int(32)  # 32 bytes per field element
BLOB_SIZE = int(4096 * 32)  # 4096 field elements of 32 bytes each
# load trusted setup
ts = ckzg.load_trusted_setup("src/trusted_setup.txt", 0)

r_square = [
    14526898881837571181,
    3129137299524312099,
    419701826671360399,
    524908885293268753,
]

q0 = 18446744069414584321
q1 = 6034159408538082302
q2 = 3691218898639771653
q3 = 8353516859464449352

q_inv_neg = 18446744069414584319

# madd0 hi = a*b + c (discards lo bits)
def madd0(a, b, c):
    sum = a * b + c
    return sum >> 64 

# madd1 hi, lo = a*b + c
def madd1(a, b, c):
    sum = a * b + c
    return sum >> 64, sum & ((1 << 64) - 1)

# madd2 hi, lo = a*b + c + d
def madd2(a, b, c, d):
    sum = a * b + c + d
    return sum >> 64, sum & ((1 << 64) - 1)

def mul64(x: int, y: int) -> (int, int):
    mask32 = (1 << 32) - 1
    x0 = x & mask32
    x1 = x >> 32
    y0 = y & mask32
    y1 = y >> 32

    w0 = x0 * y0
    t = x1 * y0 + (w0 >> 32)
    w1 = t & mask32
    w2 = t >> 32
    w1 += x0 * y1
    hi = x1 * y1 + w2 + (w1 >> 32)
    lo = x * y

    return hi, lo & ((1 << 64) - 1)

def add64(x: int, y: int, carry: int) -> (int, int):
    sum = x + y + carry
    return sum & ((1 << 64) - 1), sum >> 64


def sub64(x: int, y: int, borrow: int) -> (int, int):
    diff = x - y - borrow
    return diff & ((1 << 64) - 1), diff >> 64

def to_mont(x):
    if len(x) != 4:
        raise ValueError("toMont: invalid input length")

    t0, t1, t2, t3 = 0, 0, 0, 0
    u0, u1, u2, u3 = 0, 0, 0, 0

    # First block
    c0, c1, c2 = 0, 0, 0
    v = x[0]
    u0, t0 = mul64(v, r_square[0])
    u1, t1 = mul64(v, r_square[1])
    u2, t2 = mul64(v, r_square[2])
    u3, t3 = mul64(v, r_square[3])
    t1, c0 = add64(u0, t1, 0)
    t2, c0 = add64(u1, t2, c0)
    t3, c0 = add64(u2, t3, c0)
    c2, _ = add64(u3, 0, c0)

    m = (q_inv_neg * t0) & ((1 << 64) - 1)

    u0, c1 = mul64(m, q0)
    _, c0 = add64(t0, c1, 0)
    u1, c1 = mul64(m, q1)
    t0, c0 = add64(t1, c1, c0)
    u2, c1 = mul64(m, q2)
    t1, c0 = add64(t2, c1, c0)
    u3, c1 = mul64(m, q3)

    t2, c0 = add64(0, c1, c0)
    u3, _ = add64(u3, 0, c0)
    t0, c0 = add64(u0, t0, 0)
    t1, c0 = add64(u1, t1, c0)
    t2, c0 = add64(u2, t2, c0)
    c2, _ = add64(c2, 0, c0)
    t2, c0 = add64(t3, t2, 0)
    t3, _ = add64(u3, c2, c0)

    # Second block
    c0, c1, c2 = 0, 0, 0
    v = x[1]
    u0, c1 = mul64(v, r_square[0])
    t0, c0 = add64(c1, t0, 0)
    u1, c1 = mul64(v, r_square[1])
    t1, c0 = add64(c1, t1, c0)
    u2, c1 = mul64(v, r_square[2])
    t2, c0 = add64(c1, t2, c0)
    u3, c1 = mul64(v, r_square[3])
    t3, c0 = add64(c1, t3, c0)

    c2, _ = add64(0, 0, c0)
    t1, c0 = add64(u0, t1, 0)
    t2, c0 = add64(u1, t2, c0)
    t3, c0 = add64(u2, t3, c0)
    c2, _ = add64(u3, c2, c0)

    m = (q_inv_neg * t0) & ((1 << 64) - 1)

    u0, c1 = mul64(m, q0)
    _, c0 = add64(t0, c1, 0)
    u1, c1 = mul64(m, q1)
    t0, c0 = add64(t1, c1, c0)
    u2, c1 = mul64(m, q2)
    t1, c0 = add64(t2, c1, c0)
    u3, c1 = mul64(m, q3)

    t2, c0 = add64(0, c1, c0)
    u3, _ = add64(u3, 0, c0)
    t0, c0 = add64(u0, t0, 0)
    t1, c0 = add64(u1, t1, c0)
    t2, c0 = add64(u2, t2, c0)
    c2, _ = add64(c2, 0, c0)
    t2, c0 = add64(t3, t2, 0)
    t3, _ = add64(u3, c2, c0)

    # Third block
    c0, c1, c2 = 0, 0, 0
    v = x[2]
    u0, c1 = mul64(v, r_square[0])
    t0, c0 = add64(c1, t0, 0)
    u1, c1 = mul64(v, r_square[1])
    t1, c0 = add64(c1, t1, c0)
    u2, c1 = mul64(v, r_square[2])
    t2, c0 = add64(c1, t2, c0)
    u3, c1 = mul64(v, r_square[3])
    t3, c0 = add64(c1, t3, c0)

    c2, _ = add64(0, 0, c0)
    t1, c0 = add64(u0, t1, 0)
    t2, c0 = add64(u1, t2, c0)
    t3, c0 = add64(u2, t3, c0)
    c2, _ = add64(u3, c2, c0)

    m = (q_inv_neg * t0) & ((1 << 64) - 1)

    u0, c1 = mul64(m, q0)
    _, c0 = add64(t0, c1, 0)
    u1, c1 = mul64(m, q1)
    t0, c0 = add64(t1, c1, c0)
    u2, c1 = mul64(m, q2)
    t1, c0 = add64(t2, c1, c0)
    u3, c1 = mul64(m, q3)

    t2, c0 = add64(0, c1, c0)
    u3, _ = add64(u3, 0, c0)
    t0, c0 = add64(u0, t0, 0)
    t1, c0 = add64(u1, t1, c0)
    t2, c0 = add64(u2, t2, c0)
    c2, _ = add64(c2, 0, c0)
    t2, c0 = add64(t3, t2, 0)
    t3, _ = add64(u3, c2, c0)

    # Fourth block
    c0, c1, c2 = 0, 0, 0
    v = x[3]
    u0, c1 = mul64(v, r_square[0])
    t0, c0 = add64(c1, t0, 0)
    u1, c1 = mul64(v, r_square[1])
    t1, c0 = add64(c1, t1, c0)
    u2, c1 = mul64(v, r_square[2])
    t2, c0 = add64(c1, t2, c0)
    u3, c1 = mul64(v, r_square[3])
    t3, c0 = add64(c1, t3, c0)

    c2, _ = add64(0, 0, c0)
    t1, c0 = add64(u0, t1, 0)
    t2, c0 = add64(u1, t2, c0)
    t3, c0 = add64(u2, t3, c0)
    c2, _ = add64(u3, c2, c0)

    m = (q_inv_neg * t0) & ((1 << 64) - 1)

    u0, c1 = mul64(m, q0)
    _, c0 = add64(t0, c1, 0)
    u1, c1 = mul64(m, q1)
    t0, c0 = add64(t1, c1, c0)
    u2, c1 = mul64(m, q2)
    t1, c0 = add64(t2, c1, c0)
    u3, c1 = mul64(m, q3)

    t2, c0 = add64(0, c1, c0)
    u3, _ = add64(u3, 0, c0)
    t0, c0 = add64(u0, t0, 0)
    t1, c0 = add64(u1, t1, c0)
    t2, c0 = add64(u2, t2, c0)
    c2, _ = add64(c2, 0, c0)
    t2, c0 = add64(t3, t2, 0)
    t3, _ = add64(u3, c2, c0)

    result = [t0, t1, t2, t3]
    if not smaller_than_modulus(result):
        b = 0
        result[0], b = sub64(result[0], q0, 0)
        result[1], b = sub64(result[1], q1, b)
        result[2], b = sub64(result[2], q2, b)
        result[3], _ = sub64(result[3], q3, b)

    return result

# FromMont function
def from_mont(z): # pylint: disable=N806
    m = (z[0] * q_inv_neg) & ((1 << 64) - 1)
    C = madd0(m, q0, z[0])
    C, z[0] = madd2(m, q1, z[1], C)
    C, z[1] = madd2(m, q2, z[2], C)
    C, z[2] = madd2(m, q3, z[3], C)
    z[3] = C

    m = (z[0] * q_inv_neg) & ((1 << 64) - 1)
    C = madd0(m, q0, z[0])
    C, z[0] = madd2(m, q1, z[1], C)
    C, z[1] = madd2(m, q2, z[2], C)
    C, z[2] = madd2(m, q3, z[3], C)
    z[3] = C

    m = (z[0] * q_inv_neg) & ((1 << 64) - 1)
    C = madd0(m, q0, z[0])
    C, z[0] = madd2(m, q1, z[1], C)
    C, z[1] = madd2(m, q2, z[2], C)
    C, z[2] = madd2(m, q3, z[3], C)
    z[3] = C

    m = (z[0] * q_inv_neg) & ((1 << 64) - 1)
    C = madd0(m, q0, z[0])
    C, z[0] = madd2(m, q1, z[1], C)
    C, z[1] = madd2(m, q2, z[2], C)
    C, z[2] = madd2(m, q3, z[3], C)
    z[3] = C

    if not smaller_than_modulus(z):
        b = 0
        z[0], b = sub64(z[0], q0, 0)
        z[1], b = sub64(z[1], q1, b)
        z[2], b = sub64(z[2], q2, b)
        z[3], _ = sub64(z[3], q3, b)

def smaller_than_modulus(z):
    """Check if z is smaller than the modulus."""
    return z[3] < q3 or (z[3] == q3 and
                         (z[2] < q2 or (z[2] == q2 and (z[1] < q1 or (z[1] == q1 and z[0] < q0)))))

def rand_field_element():
    """Generate a random field element."""
    bs = os.urandom(32)
    r = [0] * 4
    r[3] = struct.unpack(">Q", bs[:8])[0]
    r[2] = struct.unpack(">Q", bs[8:16])[0]
    r[1] = struct.unpack(">Q", bs[16:24])[0]
    r[0] = struct.unpack(">Q", bs[24:32])[0]

    z = to_mont(r)
    from_mont(z)

    result = bytearray(32)
    struct.pack_into(">Q", result, 24, z[0])
    struct.pack_into(">Q", result, 16, z[1])
    struct.pack_into(">Q", result, 8, z[2])
    struct.pack_into(">Q", result, 0, z[3])

    return bytes(result)

"""
Helper functions
"""


def ceiling_division(a: int, b: int) -> int:
    """
    Calculate ceil without using floating point.
    Used by many of the EVM's formulas.
    """
    return -(a // -b)


def compute_create_address(
    *,
    address: FixedSizeBytesConvertible | EOA,
    nonce: int | None = None,
    salt: int = 0,
    initcode: BytesConvertible = b"",
    opcode: Op = Op.CREATE,
) -> Address:
    """
    Compute address of the resulting contract created using a transaction
    or the `CREATE` opcode.
    """
    if opcode == Op.CREATE:
        if isinstance(address, EOA):
            if nonce is None:
                nonce = address.nonce
        else:
            address = Address(address)
        if nonce is None:
            nonce = 0
        hash_bytes = Bytes(encode([address, int_to_bytes(nonce)])).keccak256()
        return Address(hash_bytes[-20:])
    if opcode == Op.CREATE2:
        return compute_create2_address(address, salt, initcode)
    raise ValueError("Unsupported opcode")


def compute_create2_address(
    address: FixedSizeBytesConvertible, salt: FixedSizeBytesConvertible, initcode: BytesConvertible
) -> Address:
    """
    Compute address of the resulting contract created using the `CREATE2`
    opcode.
    """
    hash_bytes = Bytes(
        b"\xff" + Address(address) + Hash(salt) + Bytes(initcode).keccak256()
    ).keccak256()
    return Address(hash_bytes[-20:])


def compute_eofcreate_address(
    address: FixedSizeBytesConvertible,
    salt: FixedSizeBytesConvertible,
    init_container: BytesConvertible,
) -> Address:
    """Compute address of the resulting contract created using the `EOFCREATE` opcode."""
    hash_bytes = Bytes(
        b"\xff" + Address(address) + Hash(salt) + Bytes(init_container).keccak256()
    ).keccak256()
    return Address(hash_bytes[-20:])


def add_kzg_version(
    b_hashes: List[bytes | SupportsBytes | int | str], kzg_version: int
) -> List[Hash]:
    """Add  Kzg Version to each blob hash."""
    kzg_version_hex = bytes([kzg_version])
    kzg_versioned_hashes = []

    for b_hash in b_hashes:
        b_hash = bytes(Hash(b_hash))
        if isinstance(b_hash, int) or isinstance(b_hash, str):
            kzg_versioned_hashes.append(Hash(kzg_version_hex + b_hash[1:]))
        elif isinstance(b_hash, bytes) or isinstance(b_hash, SupportsBytes):
            if isinstance(b_hash, SupportsBytes):
                b_hash = bytes(b_hash)
            kzg_versioned_hashes.append(Hash(kzg_version_hex + b_hash[1:]))
        else:
            raise TypeError("Blob hash must be either an integer, string or bytes")
    return kzg_versioned_hashes

def generate_random_blob() -> bytes:
    """
    Generate a random blob.
    :return: A random blob.
    """
    return b"".join(rand_field_element() for _ in range(4096))

def blob_to_kzg_commitment(blob: bytes) -> bytes:
    """
    Convert a blob to a commitment.
    :param blob: The blob to convert.
    :return: The commitment.
    """
    return ckzg.blob_to_kzg_commitment(blob, ts)

def compute_blob_kzg_proof(blob: bytes, commitment: bytes) -> bytes:
    """
    Compute a KZG proof.
    :param blob: The blob to prove.
    :param commitment: The commitment to prove against.
    :return: The proof.
    """
    return ckzg.compute_blob_kzg_proof(blob, commitment, ts)

@dataclass(kw_only=True, frozen=True, repr=False)
class TestParameterGroup:
    """
    Base class for grouping test parameters in a dataclass. Provides a generic
    __repr__ method to generate clean test ids, including only non-default
    optional fields.
    """

    __test__ = False  # explicitly prevent pytest collecting this class

    def __repr__(self):
        """
        Generate repr string, intended to be used as a test id, based on the class
        name and the values of the non-default optional fields.
        """
        class_name = self.__class__.__name__
        field_strings = []

        for field in fields(self):
            value = getattr(self, field.name)
            # Include the field only if it is not optional or not set to its default value
            if field.default is MISSING or field.default != value:
                field_strings.append(f"{field.name}_{value}")

        return f"{class_name}_{'-'.join(field_strings)}"
