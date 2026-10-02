"""
The worked example in examples/consumer.py, run.

An example nobody runs is a comment that rots. These tests deploy the file
exactly as it ships and check the guards it exists to demonstrate: the
storage view that works on this network, a status that actually carries a
fact, and a reading newer than the consumer's own commitment.

SIGNAL itself is answered by a stub, because direct mode loads one contract
per process.
"""

import sys
from pathlib import Path

import pytest

from test.stub_signal import (
    EARLIER,
    FEED,
    KEY,
    LATER,
    OPENED,
    VIEW_LATEST_DECIDED,
    SignalStub,
)

EXAMPLE = str(Path(__file__).resolve().parent.parent / "examples" / "consumer.py")


def set_date(vm, stamp: str) -> None:
    """Move the transaction date, which is what a contract stamps itself with."""
    vm.warp(stamp)
    message = sys.modules.get("genlayer.message")
    if message is not None and isinstance(getattr(message, "raw", None), dict):
        message.raw["datetime"] = stamp
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = stamp


@pytest.fixture
def oracle(direct_vm):
    return SignalStub().install(direct_vm)


@pytest.fixture
def consumer(direct_vm, direct_deploy, oracle):
    # Deployed before the reading was taken, which is the ordering the
    # freshness check depends on.
    set_date(direct_vm, OPENED)
    contract = direct_deploy(EXAMPLE, signal="0x" + "dd" * 20)
    direct_vm.strict_mocks = False
    return contract


def test_the_example_acts_on_an_attested_reading(direct_vm, consumer):
    got = consumer.decide(FEED, KEY, "incident.impact")
    assert got == {"acted": True, "value": "critical"}


def test_the_example_reads_the_storage_view_that_works_on_this_network(direct_vm, consumer, oracle):
    """
    LATEST_FINALIZED would be the natural ask and it times out on Studio
    Next, so the example uses the default view. Pinned here so the example
    and the comment explaining it cannot drift apart.
    """
    consumer.decide(FEED, KEY, "incident.impact")
    assert [v["storage_view"] for v in oracle.views] == [VIEW_LATEST_DECIDED]


def test_the_example_refuses_a_key_that_was_never_read(direct_vm, consumer, oracle):
    oracle.set_reading(status="", read_at="", values={})
    got = consumer.decide(FEED, KEY, "incident.impact")
    assert got["acted"] is False
    assert got["why"] == "no attested reading yet"


@pytest.mark.parametrize("status", ["absent", "unreadable"])
def test_the_example_acts_on_neither_absent_nor_unreadable(direct_vm, consumer, oracle, status):
    """Neither is a fact about the world, so neither may be acted on."""
    oracle.set_reading(status=status)
    assert consumer.decide(FEED, KEY, "incident.impact")["acted"] is False


def test_the_example_refuses_a_reading_older_than_itself(direct_vm, consumer, oracle):
    oracle.set_reading(read_at=EARLIER)
    got = consumer.decide(FEED, KEY, "incident.impact")
    assert got["acted"] is False
    assert got["why"] == "that reading predates this contract"


def test_the_example_accepts_a_reading_taken_after_it(direct_vm, consumer, oracle):
    oracle.set_reading(read_at=LATER)
    assert consumer.decide(FEED, KEY, "incident.impact")["acted"] is True
