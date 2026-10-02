# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
"""
SIGNAL. An attested reader: web facts that every validator derived.

A contract that needs a fact from the web has three problems. It cannot let
the caller supply the URL, because whoever names the document has appointed
themselves the judge. It cannot store whatever the leader saw, because a
leader that lies is the whole threat model. And it cannot treat "the page
said nothing" and "the page could not be read" as the same thing, because
one of those is a claim about the world and the other is a claim about the
network.

SIGNAL is the primitive that solves those three once, so a consumer contract
does not have to solve them again.

    register(name, host, path, fields)   fix a source, immutably
    read(feed_id, key)                   take a reading under consensus
    get_reading(feed_id, key)            what consensus agreed, as a view

A feed is registered by somebody, and its id carries that somebody's address:
`0xabc...:github`. Nobody can squat the name `github`, and a consumer always
knows whose source it is trusting. Once registered, a feed never changes: the
host, the path template and the fields are fixed, so the document a reading
points at cannot be moved after a consumer has come to depend on it.

Every value this contract stores is derived by every validator:

    status      each validator fetched the document itself
    values      each validator extracted the same fields from its own copy
    url         built by the contract from the registry and the key
    read_at     the transaction's own datetime, part of the message
    feed, key   the arguments, echoed, and the url proves what they built

Nothing here is copied from the leader. A validator that read the document
cannot agree that it was unreadable, and a validator that could not read it
cannot attest to any value at all. Both are refusals, not opinions.

No model is involved anywhere. Validators fetch and compare strings.
"""

from dataclasses import dataclass

import genlayer as gl
from genlayer.types import *

from contracts.reading import (
    ABSENT,
    READ,
    UNREADABLE,
    extract,
    join_values,
    parse_fields,
    split_values,
    valid_host,
    valid_key,
    valid_path,
)


@gl.storage.allow
@dataclass
class Feed:
    host: str
    path: str
    fields: str
    creator: Address
    registered_at: str


@gl.storage.allow
@dataclass
class Reading:
    feed: str
    key: str
    status: str
    values: str
    url: str
    read_at: str


class Signal(gl.contract.Contract):
    feeds: gl.storage.TreeMap[str, Feed]
    feed_ids: gl.storage.DynArray[str]
    # Latest reading per feed and key, overwritten rather than appended, so a
    # feed that is read every hour does not grow the contract without bound.
    #
    # Latest wins: a later reading of the same feed and key replaces the
    # earlier one. Anyone may call `read`, so anyone can refresh a record,
    # including with a reading taken while the source happened to be down.
    # That can delay a consumer, never redirect it: a consumer decides on
    # `status` and `read_at`, and taking a fresh reading is equally open to
    # whoever is waiting on it.
    readings: gl.storage.TreeMap[str, Reading]

    def __init__(self):
        pass

    # ----------------------------------------------------------------
    # sources
    # ----------------------------------------------------------------

    @gl.public.write
    def register(self, name: str, host: str, path: str, fields: str) -> dict:
        """
        Fix a source. The id is namespaced by the caller, so `github` is not
        a name anyone can take from anyone else, and a consumer can see whose
        feed it is about to trust.

        A feed cannot be edited or removed afterwards. That is the guarantee
        a consumer is relying on: the document it reads today is built from
        the same host and the same template as the one it read last week.
        """
        label = name.strip().lower()
        if not label or len(label) > 40:
            raise gl.vm.UserError("name the feed")
        for ch in label:
            if not (("0" <= ch <= "9") or ("a" <= ch <= "z") or ch in "-_"):
                raise gl.vm.UserError("a feed name is letters, digits, hyphen or underscore")

        owner = gl.message.sender_address
        feed_id = owner.as_hex.lower() + ":" + label
        if feed_id in self.feeds:
            raise gl.vm.UserError("that feed already exists and cannot be changed")

        clean_host = host.strip().lower()
        if not valid_host(clean_host):
            raise gl.vm.UserError("host must be a bare hostname, with no scheme, port or path")
        clean_path = path.strip()
        if not valid_path(clean_path):
            raise gl.vm.UserError("path must start at / and contain {key} exactly once")
        # Raises on a malformed list, which refuses the registration.
        paths = parse_fields(fields)

        self.feeds[feed_id] = Feed(
            host=clean_host,
            path=clean_path,
            fields=",".join(paths),
            creator=owner,
            registered_at=_stamp(),
        )
        self.feed_ids.append(feed_id)
        return self.get_feed(feed_id)

    # ----------------------------------------------------------------
    # readings
    # ----------------------------------------------------------------

    @gl.public.write
    def read(self, feed_id: str, key: str) -> dict:
        """
        Take a reading, under consensus, and store what every validator
        agreed on.

        Callable by anyone: there is nothing to bias. The URL comes from the
        registry, the fields come from the registry, and the only thing the
        caller contributes is which key to look up, which is checked and then
        written into the record so anyone can see what was asked for.
        """
        fid = feed_id.strip().lower()
        if fid not in self.feeds:
            raise gl.vm.UserError("no such feed: " + fid)
        feed = self.feeds[fid]

        ref = key.strip()
        if not valid_key(ref):
            raise gl.vm.UserError("a key is ASCII letters, digits, hyphen or underscore")

        url = "https://" + feed.host + feed.path.replace("{key}", ref)
        paths = [p for p in feed.fields.split(",") if p]

        def leader_fn():
            return _probe(url, paths)

        def validator_fn(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return False
            leader = leaders_res.calldata
            if not isinstance(leader, dict) or "status" not in leader or "values" not in leader:
                # A result of the wrong shape is a disagreement, not a crash.
                return False
            mine = _probe(url, paths)

            # I could not read it. The only honest thing I can agree with is
            # that it could not be read. I cannot attest to any value.
            if mine["status"] == UNREADABLE:
                return str(leader["status"]) == UNREADABLE

            # I read it. Then it was not unreadable, whatever the leader says:
            # "broken" and "says nothing" are different claims about the world.
            if str(leader["status"]) == UNREADABLE:
                return False

            return str(leader["status"]) == mine["status"] and str(leader["values"]) == mine["values"]

        agreed = gl.vm.run_nondet(leader_fn, validator_fn)

        status = str(agreed["status"])
        values = str(agreed["values"])
        if status not in (READ, ABSENT, UNREADABLE):
            raise gl.vm.UserError("unknown reading status")

        record = Reading(
            feed=fid,
            key=ref,
            status=status,
            values=values if status != UNREADABLE else "",
            url=url,
            read_at=_stamp(),
        )
        self.readings[_slot(fid, ref)] = record
        return _reading_dict(record, paths)

    # ----------------------------------------------------------------
    # reading back
    # ----------------------------------------------------------------

    @gl.public.view
    def get_reading(self, feed_id: str, key: str) -> dict:
        """
        The latest agreed reading, or a record with status "" if this feed
        and key have never been read. Consumers check `status` and `read_at`
        rather than assuming a reading exists.
        """
        fid = feed_id.strip().lower()
        ref = key.strip()
        slot = _slot(fid, ref)
        if slot not in self.readings:
            return {
                "feed": fid,
                "key": ref,
                "status": "",
                "values": {},
                "url": "",
                "read_at": "",
            }
        paths = []
        if fid in self.feeds:
            paths = [p for p in self.feeds[fid].fields.split(",") if p]
        return _reading_dict(self.readings[slot], paths)

    @gl.public.view
    def value_of(self, feed_id: str, key: str, field: str) -> str:
        """
        One field of the latest reading, as text, or "" if it is not there.

        The narrow view a consumer contract wants: one call, one string, no
        structure to walk. "" means the field was absent, the reading failed,
        or nothing has ever been read, and `get_reading` says which.
        """
        record = self.get_reading(feed_id, key)
        values = record["values"]
        if not isinstance(values, dict):
            return ""
        return str(values.get(field.strip(), ""))

    @gl.public.view
    def get_feed(self, feed_id: str) -> dict:
        fid = feed_id.strip().lower()
        if fid not in self.feeds:
            raise gl.vm.UserError("no such feed: " + fid)
        feed = self.feeds[fid]
        return {
            "feed_id": fid,
            "host": feed.host,
            "path": feed.path,
            "fields": [p for p in feed.fields.split(",") if p],
            "creator": feed.creator.as_hex,
            "registered_at": feed.registered_at,
            "example_url": "https://" + feed.host + feed.path,
        }

    @gl.public.view
    def feed_list(self) -> list:
        return [f for f in self.feed_ids]

    @gl.public.view
    def count(self) -> int:
        return len(self.feed_ids)


# --------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------


def _slot(feed_id: str, key: str) -> str:
    return feed_id + "|" + key


def _stamp() -> str:
    """
    The transaction's own datetime, which every validator in the round sees
    identically because it is part of the message rather than a clock read.
    """
    return str(gl.message.raw["datetime"])


def _probe(url: str, paths: list) -> dict:
    """
    Fetch once and say exactly what happened. Returns primitives only, so the
    whole result is comparable field by field between validators.

    A 404 is the source answering: there is nothing under this key, which is
    `absent`. Any other failure, including a timeout, a server error or a
    body that is not JSON, is `unreadable`: it says nothing about the world,
    only about the attempt.
    """
    import json

    try:
        resp = gl.nondet.web.get(url)
        status = int(resp.status)
        body = (resp.body or b"").decode("utf-8", errors="replace")
    except Exception:
        return {"status": UNREADABLE, "values": ""}

    if status == 404:
        return {"status": ABSENT, "values": join_values(["" for _ in paths])}
    if status < 200 or status >= 300:
        return {"status": UNREADABLE, "values": ""}

    try:
        document = json.loads(body)
    except Exception:
        return {"status": UNREADABLE, "values": ""}

    values, present = extract(document, paths)
    try:
        blob = join_values(values)
    except ValueError:
        # A value with a newline in it cannot be stored unambiguously, so the
        # document counts as unreadable rather than being silently mangled.
        return {"status": UNREADABLE, "values": ""}
    return {"status": READ if present else ABSENT, "values": blob}


def _reading_dict(record: Reading, paths: list) -> dict:
    values = split_values(record.values, len(paths))
    return {
        "feed": record.feed,
        "key": record.key,
        "status": record.status,
        "values": {paths[i]: values[i] for i in range(len(paths))},
        "url": record.url,
        "read_at": record.read_at,
    }
