"""
SIGNAL run for real, in-process, by genlayer-test's direct mode.

No chain and no network: the feed's host answers with a real GitHub incident
record saved in fixtures/, and the transaction date is set per test.

Half of these tests run the validator side, because a leader that reaches
the right answer proves nothing. What matters is whether an honest validator
would agree, and whether a dishonest one would be caught. Each lie here is
one a leader would actually have a reason to tell: hide a record, change a
value, call a working page broken, or call a missing page a reading.
"""

import json
import sys
from pathlib import Path

import pytest

BUNDLE = str(Path(__file__).resolve().parent.parent / "contracts" / "signal_bundle.py")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

HOST = "www.githubstatus.com"
PATH = "/api/v2/incidents/{key}.json"
FIELDS = "incident.id,incident.created_at,incident.resolved_at,incident.impact"

REF = "zkxwbgr0cnmx"  # real GitHub incident: critical, 2026-08-17
OWNER = b"\xa0" * 20
STRANGER = b"\xb0" * 20

READ, ABSENT, UNREADABLE = "read", "absent", "unreadable"


def incident() -> dict:
    return json.loads((FIXTURES / f"github_{REF}.json").read_text(encoding="utf-8"))


def serve(vm, key: str, body=None, status: int = 200, host: str = HOST) -> None:
    """Answer the feed's URL for `key`, with the real record by default."""
    vm.clear_mocks()
    if body is None:
        body = incident()
    text = body if isinstance(body, str) else json.dumps(body)
    pattern = host.replace(".", r"\.") + r"/api/v2/incidents/" + key + r"\.json"
    vm.mock_web(pattern, {"status": status, "body": text})


def serve_url(vm, url: str, body, status: int = 200) -> None:
    """Answer one exact URL, for feeds that are not the status page."""
    vm.clear_mocks()
    text = body if isinstance(body, str) else json.dumps(body)
    pattern = url.replace(".", r"\.").replace("?", r"\?")
    vm.mock_web(pattern, {"status": status, "body": text})


def set_date(vm, stamp: str) -> None:
    """Move the transaction date, which is also what SIGNAL stamps readings with."""
    vm.warp(stamp)
    message = sys.modules.get("genlayer.message")
    if message is not None and isinstance(getattr(message, "raw", None), dict):
        message.raw["datetime"] = stamp
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = stamp


@pytest.fixture
def signal(direct_vm, direct_deploy):
    contract = direct_deploy(BUNDLE)
    direct_vm.strict_mocks = False
    set_date(direct_vm, "2026-09-01T09:00:00Z")
    return contract


@pytest.fixture
def feed(direct_vm, signal):
    with direct_vm.prank(OWNER):
        got = signal.register("github", HOST, PATH, FIELDS)
    return got["feed_id"]


def leader(status: str, values: list) -> dict:
    """The shape SIGNAL's leader returns, so a test can fake a dishonest one."""
    return {"status": status, "values": "\n".join(values)}


REAL_VALUES = [REF, "2026-08-17T13:40:03.629Z", "2026-08-17T21:15:46.623Z", "critical"]


# --------------------------------------------------------------------
# registering a source
# --------------------------------------------------------------------


def test_a_feed_id_carries_the_address_that_registered_it(direct_vm, signal):
    with direct_vm.prank(OWNER):
        got = signal.register("github", HOST, PATH, FIELDS)
    assert got["feed_id"] == "0x" + OWNER.hex() + ":github"
    assert got["host"] == HOST
    assert got["fields"] == FIELDS.split(",")
    assert signal.count() == 1


def test_nobody_can_squat_a_name_because_the_id_includes_the_registrar(direct_vm, signal):
    with direct_vm.prank(OWNER):
        mine = signal.register("github", HOST, PATH, FIELDS)
    with direct_vm.prank(STRANGER):
        theirs = signal.register("github", HOST, PATH, FIELDS)
    assert mine["feed_id"] != theirs["feed_id"]
    assert signal.count() == 2


def test_a_feed_cannot_be_registered_twice_so_it_cannot_be_moved(direct_vm, signal):
    with direct_vm.prank(OWNER):
        signal.register("github", HOST, PATH, FIELDS)
        with direct_vm.expect_revert("cannot be changed"):
            signal.register("github", "evil.example.com", PATH, FIELDS)


@pytest.mark.parametrize(
    "host",
    ["https://www.githubstatus.com", "www.githubstatus.com/api", "localhost", "host:8080", ""],
)
def test_a_host_that_is_not_a_bare_hostname_is_refused(direct_vm, signal, host):
    with direct_vm.prank(OWNER):
        with direct_vm.expect_revert("bare hostname"):
            signal.register("github", host, PATH, FIELDS)


@pytest.mark.parametrize(
    "path",
    ["api/{key}.json", "/api/{key}/{key}.json", "/api/../{key}", "/api/incidents.json", "//evil.com/{key}"],
)
def test_a_path_that_could_leave_the_template_is_refused(direct_vm, signal, path):
    with direct_vm.prank(OWNER):
        with direct_vm.expect_revert("{key} exactly once"):
            signal.register("github", HOST, path, FIELDS)


# --------------------------------------------------------------------
# taking a reading
# --------------------------------------------------------------------


def test_a_present_record_is_read_and_every_declared_field_is_stored(direct_vm, signal, feed):
    serve(direct_vm, REF)
    got = signal.read(feed, REF)

    assert got["status"] == READ
    assert got["values"]["incident.id"] == REF
    assert got["values"]["incident.impact"] == "critical"
    assert got["values"]["incident.created_at"] == "2026-08-17T13:40:03.629Z"
    # The URL is built by the contract from the registry, not by the caller.
    assert got["url"] == "https://" + HOST + "/api/v2/incidents/" + REF + ".json"
    assert got["read_at"] == "2026-09-01T09:00:00Z"
    assert direct_vm.run_validator() is True


def test_a_reading_is_readable_again_as_a_view(direct_vm, signal, feed):
    serve(direct_vm, REF)
    signal.read(feed, REF)

    stored = signal.get_reading(feed, REF)
    assert stored["status"] == READ
    assert stored["values"]["incident.impact"] == "critical"
    assert signal.value_of(feed, REF, "incident.impact") == "critical"
    assert signal.value_of(feed, REF, "incident.nothing") == ""


def test_a_key_that_was_never_read_says_so_rather_than_inventing_a_record(signal, feed):
    stored = signal.get_reading(feed, "neverread")
    assert stored["status"] == ""
    assert stored["read_at"] == ""
    assert stored["values"] == {}


def test_a_missing_document_is_absent_not_unreadable(direct_vm, signal, feed):
    """404 is the source answering: there is nothing under this key."""
    serve(direct_vm, "gone1234", "not found", status=404)
    got = signal.read(feed, "gone1234")

    assert got["status"] == ABSENT
    assert got["values"]["incident.id"] == ""
    assert direct_vm.run_validator() is True


def test_a_document_without_the_declared_fields_is_absent(direct_vm, signal, feed):
    serve(direct_vm, "empty123", {"page": {"id": "x"}})
    got = signal.read(feed, "empty123")

    assert got["status"] == ABSENT
    assert direct_vm.run_validator() is True


@pytest.mark.parametrize(
    "body,status",
    [("down", 503), ("<html>maintenance</html>", 200), ("", 200), ("{not json", 200)],
)
def test_a_page_that_cannot_be_read_is_unreadable_and_stores_no_values(
    direct_vm, signal, feed, body, status
):
    serve(direct_vm, "broken12", body, status=status)
    got = signal.read(feed, "broken12")

    assert got["status"] == UNREADABLE
    assert all(v == "" for v in got["values"].values())
    assert direct_vm.run_validator() is True


def test_a_later_reading_replaces_the_earlier_one_rather_than_piling_up(direct_vm, signal, feed):
    serve(direct_vm, REF)
    signal.read(feed, REF)

    changed = incident()
    changed["incident"]["impact"] = "major"
    set_date(direct_vm, "2026-09-02T09:00:00Z")
    serve(direct_vm, REF, changed)
    signal.read(feed, REF)

    stored = signal.get_reading(feed, REF)
    assert stored["values"]["incident.impact"] == "major"
    assert stored["read_at"] == "2026-09-02T09:00:00Z"


@pytest.mark.parametrize("key", ["../secrets", "a/b", "a.b", "", "x" * 65])
def test_a_key_that_could_reach_another_document_is_refused(direct_vm, signal, feed, key):
    with direct_vm.expect_revert("ASCII letters"):
        signal.read(feed, key)


def test_reading_an_unregistered_feed_is_refused(direct_vm, signal):
    with direct_vm.expect_revert("no such feed"):
        signal.read("0xdead:github", REF)


# --------------------------------------------------------------------
# what a validator will and will not agree to
# --------------------------------------------------------------------


def read_honestly(vm, signal, feed, key=REF):
    serve(vm, key)
    return signal.read(feed, key)


def test_a_validator_rejects_a_leader_who_hides_a_readable_record(direct_vm, signal, feed):
    """Calling a working page broken would let a leader block a consumer."""
    read_honestly(direct_vm, signal, feed)
    assert direct_vm.run_validator(leader_result=leader(UNREADABLE, [])) is False


def test_a_validator_rejects_a_leader_who_changes_a_value(direct_vm, signal, feed):
    read_honestly(direct_vm, signal, feed)
    lie = leader(READ, [REF, "2026-08-17T13:40:03.629Z", "2026-08-17T21:15:46.623Z", "minor"])
    assert direct_vm.run_validator(leader_result=lie) is False


def test_a_validator_rejects_a_leader_who_moves_a_timestamp(direct_vm, signal, feed):
    read_honestly(direct_vm, signal, feed)
    lie = leader(READ, [REF, "2026-08-17T10:00:00.000Z", "2026-08-17T21:15:46.623Z", "critical"])
    assert direct_vm.run_validator(leader_result=lie) is False


def test_a_validator_rejects_a_leader_who_calls_a_present_record_absent(direct_vm, signal, feed):
    read_honestly(direct_vm, signal, feed)
    assert direct_vm.run_validator(leader_result=leader(ABSENT, ["", "", "", ""])) is False


def test_a_validator_rejects_a_leader_who_invents_a_record_for_a_missing_key(direct_vm, signal, feed):
    """The page 404s, so a value claimed about it came from nowhere."""
    serve(direct_vm, "gone1234", "not found", status=404)
    signal.read(feed, "gone1234")
    assert direct_vm.run_validator(leader_result=leader(READ, REAL_VALUES)) is False


def test_a_validator_rejects_a_leader_that_errored(direct_vm, signal, feed):
    read_honestly(direct_vm, signal, feed)
    assert direct_vm.run_validator(leader_error=Exception("boom")) is False


def test_a_validator_that_cannot_read_agrees_only_that_it_could_not_be_read(direct_vm, signal, feed):
    serve(direct_vm, "broken12", "down", status=503)
    signal.read(feed, "broken12")

    assert direct_vm.run_validator(leader_result=leader(UNREADABLE, [])) is True
    # It cannot attest to any value, however plausible.
    assert direct_vm.run_validator(leader_result=leader(READ, REAL_VALUES)) is False
    assert direct_vm.run_validator(leader_result=leader(ABSENT, ["", "", "", ""])) is False


def test_a_validator_ignores_fields_the_feed_never_declared(direct_vm, signal, feed):
    """
    A status page carries fields that move between requests. Only the declared
    paths are compared, so an honest validator does not disagree about a record
    that did not change.
    """
    read_honestly(direct_vm, signal, feed)

    moved = incident()
    moved["incident"]["name"] = "renamed since"
    moved["incident"]["incident_updates"] = []
    moved["page"] = {"updated_at": "2026-09-01T09:00:01Z"}
    serve(direct_vm, REF, moved)

    assert direct_vm.run_validator() is True


def test_a_validator_notices_a_declared_field_that_did_change(direct_vm, signal, feed):
    read_honestly(direct_vm, signal, feed)

    edited = incident()
    edited["incident"]["impact"] = "minor"
    serve(direct_vm, REF, edited)

    assert direct_vm.run_validator() is False


# --------------------------------------------------------------------
# a second source, to show this is a reader and not a status-page wrapper
#
# The npm registry: another host, another document shape, fields nested
# under a hyphenated key and one reached through a list index. The contract
# does not change for it, which is the claim being tested.
# --------------------------------------------------------------------

NPM_HOST = "registry.npmjs.org"
NPM_PATH = "/{key}"
NPM_FIELDS = "name,dist-tags.latest,maintainers.0.name,license,time.modified"
PKG = "genlayer-js"


def package() -> dict:
    return json.loads((FIXTURES / f"npm_{PKG}.json").read_text(encoding="utf-8"))


@pytest.fixture
def npm_feed(direct_vm, signal):
    with direct_vm.prank(OWNER):
        got = signal.register("npm", NPM_HOST, NPM_PATH, NPM_FIELDS)
    return got["feed_id"]


def serve_npm(vm, body=None, status: int = 200, key: str = PKG) -> None:
    serve_url(vm, f"https://{NPM_HOST}/{key}", package() if body is None else body, status)


def test_a_different_host_and_shape_needs_no_change_to_the_contract(direct_vm, signal, npm_feed):
    serve_npm(direct_vm)
    got = signal.read(npm_feed, PKG)

    assert got["status"] == READ
    assert got["values"]["name"] == PKG
    assert got["values"]["license"] == "MIT"
    assert got["url"] == f"https://{NPM_HOST}/{PKG}"
    assert direct_vm.run_validator() is True


def test_a_field_under_a_hyphenated_key_is_read(direct_vm, signal, npm_feed):
    serve_npm(direct_vm)
    got = signal.read(npm_feed, PKG)
    assert got["values"]["dist-tags.latest"] == "1.1.8"


def test_a_field_reached_through_a_list_index_is_read(direct_vm, signal, npm_feed):
    serve_npm(direct_vm)
    got = signal.read(npm_feed, PKG)
    assert got["values"]["maintainers.0.name"] == "jmlago"


def test_a_package_that_does_not_exist_is_absent_on_this_feed_too(direct_vm, signal, npm_feed):
    serve_npm(direct_vm, "Not found", status=404, key="nosuchpackage")
    got = signal.read(npm_feed, "nosuchpackage")
    assert got["status"] == ABSENT
    assert direct_vm.run_validator() is True


def test_a_validator_catches_a_changed_version_on_this_feed_too(direct_vm, signal, npm_feed):
    serve_npm(direct_vm)
    signal.read(npm_feed, PKG)

    bumped = package()
    bumped["dist-tags"]["latest"] = "9.9.9"
    serve_npm(direct_vm, bumped)
    assert direct_vm.run_validator() is False


def test_two_feeds_on_one_contract_keep_their_own_readings(direct_vm, signal, feed, npm_feed):
    """Readings are slotted by feed and key, so sources cannot overwrite each other."""
    serve(direct_vm, REF)
    signal.read(feed, REF)
    serve_npm(direct_vm)
    signal.read(npm_feed, PKG)

    assert signal.value_of(feed, REF, "incident.impact") == "critical"
    assert signal.value_of(npm_feed, PKG, "license") == "MIT"
    assert signal.count() == 2
