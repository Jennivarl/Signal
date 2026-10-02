# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
"""
The whole of what a contract needs to consume SIGNAL.

Not part of the deployed system: this is the fifteen lines a third contract
writes to depend on an attested fact, and it is here so nobody has to read
WARRANT to work out the pattern.

Two things matter, and both are in `decide` below:

    check the status   "" means nobody has ever read this key, `absent` and
                       `unreadable` are not facts about the world, and only
                       `read` carries a value worth acting on
    check read_at      a reading older than your own commitment says nothing
                       about it, so compare it with your own timestamp

The reading is already agreed by every validator, so there is no oracle to
call, no signature to check and nothing for the caller to supply.

On the storage view: asking for `StorageView.LATEST_FINALIZED` would be the
natural way to refuse a reading consensus could still roll back, and that
read times out on Studio Next. The same call against the same contract,
differing in nothing else, returns with the default view and times out with
the finalized one:

    default view     0x5c6dcfe234f7c26141e14867b6b2902059a563ae90494ff7f1ba1a4de39f41cc
    latest finalized 0x1aaccb970988179aefcf40bac205fc8561316beaa69caa3d0de88ed95ed2513c

So this reads the default view. That is fine for a contract that only reads.
A contract that moves money on a reading needs the rollback window covered
some other way, and WARRANT does it with elapsed time: it pays only on a
reading that has existed for an hour. See https://github.com/Jennivarl/Warrant
"""

import genlayer as gl
from genlayer.types import *


class Consumer(gl.contract.Contract):
    signal: Address
    since: str

    def __init__(self, signal: str):
        self.signal = Address(signal)
        self.since = str(gl.message.raw["datetime"])

    @gl.public.write
    def decide(self, feed_id: str, key: str, field: str) -> dict:
        record = gl.contract.get_at(self.signal).view().get_reading(feed_id, key)
        if str(record["status"]) != "read":
            return {"acted": False, "why": "no attested reading yet"}
        if str(record["read_at"]) <= self.since:
            return {"acted": False, "why": "that reading predates this contract"}
        return {"acted": True, "value": str(record["values"][field])}
