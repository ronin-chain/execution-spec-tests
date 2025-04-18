"""Defines models for index files and consume test cases."""

import datetime
from pathlib import Path
from typing import List, TextIO

from pydantic import BaseModel, RootModel

from ethereum_test_base_types import HexNumber
from ethereum_test_fixtures import FixtureFormat

from .base import BaseFixture
from .file import Fixtures


class TestCaseBase(BaseModel):
    """Base model for a test case used in EEST consume commands."""

    id: str
    fixture_hash: HexNumber | None
    fork: str | None
    format: FixtureFormat
    __test__ = False  # stop pytest from collecting this class as a test


class TestCaseStream(TestCaseBase):
    """The test case model used to load test cases from a stream (stdin)."""

    fixture: BaseFixture
    __test__ = False  # stop pytest from collecting this class as a test


class TestCaseIndexFile(TestCaseBase):
    """The test case model used to save/load test cases to/from an index file."""

    json_path: Path
    __test__ = False  # stop pytest from collecting this class as a test

    # TODO: add pytest marks
    """
    ConsumerTypes = Literal["all", "direct", "rlp", "engine"]
    @classmethod
    def _marks_default(cls):
        return {consumer_type: [] for consumer_type in get_args(ConsumerTypes)}
    marks: Mapping[ConsumerTypes, List[pytest.MarkDecorator]] = field(
        default_factory=lambda: TestCase._marks_default()
    )
    """


class IndexFile(BaseModel):
    """The model definition used for fixture index files."""

    root_hash: HexNumber | None
    created_at: datetime.datetime
    test_count: int
    test_cases: List[TestCaseIndexFile]


class TestCases(RootModel):
    """Root model defining a list test cases used in consume commands."""

    root: List[TestCaseIndexFile] | List[TestCaseStream]
    __test__ = False  # stop pytest from collecting this class as a test

    def __len__(self):
        """Return the number of test cases in the root list."""
        return len(self.root)

    def __getitem__(self, position):
        """Retrieve a test case by its index."""
        return self.root[position]

    def __setitem__(self, position, value):
        """Set a test case at a particular index."""
        self.root[position] = value

    def __delitem__(self, position):
        """Remove a test case at a particular index."""
        del self.root[position]

    def append(self, item):
        """Append a test case to the root list."""
        self.root.append(item)

    def insert(self, position, value):
        """Insert a test case at a given position."""
        self.root.insert(position, value)

    def remove(self, value):
        """Remove a test case from the root list."""
        self.root.remove(value)

    def pop(self, position=-1):
        """Remove and return a test case at the given position."""
        return self.root.pop(position)

    def clear(self):
        """Remove all items from the root list."""
        self.root.clear()

    def __iter__(self):
        """Return an iterator for the root list."""
        return iter(self.root)

    def __repr__(self):
        """Return a string representation of the TestCases object."""
        return f"{self.__class__.__name__}(root={self.root})"

    @classmethod
    def from_stream(cls, fd: TextIO) -> "TestCases":
        """Create a TestCases object from a stream."""
        fixtures: Fixtures = Fixtures.model_validate_json(fd.read())
        test_cases = [
            TestCaseStream(
                id=fixture_name,
                fixture_hash=fixture.hash,
                fork=fixture.get_fork(),
                format=fixture.__class__,
                fixture=fixture,
            )
            for fixture_name, fixture in fixtures.items()
        ]
        return cls(root=test_cases)

    @classmethod
    def from_index_file(cls, index_file: Path) -> "TestCases":
        """Create a TestCases object from an index file."""
        index: IndexFile = IndexFile.model_validate_json(index_file.read_text())
        return cls(root=index.test_cases)
