"""
The arithmetic SIGNAL rests on, tested on its own.

No chain and no network here. If any of these are wrong, two validators can
read the same document and store different things, which is the one failure
this design exists to prevent.
"""

import pytest

from contracts.reading import (
    ABSENT,
    READ,
    UNREADABLE,
    extract,
    join_values,
    parse_fields,
    pick,
    split_values,
    valid_host,
    valid_key,
    valid_path,
)

# ----------------------------------------------------------------------
# what a feed may be registered with
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["www.githubstatus.com", "discordstatus.com", "api.example.co.uk", "a1-b2.example.org"],
)
def test_real_hostnames_are_accepted(host):
    assert valid_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "   ",
        "localhost",  # no dot, so not a public name
        "https://evil.com",  # a scheme is not a host
        "evil.com/path",  # a path is not a host
        "evil.com:8080",  # a port could redirect the read
        "user@evil.com",  # credentials
        "evil..com",
        ".evil.com",
        "evil.com.",
        "evil.com evil2.com",
        "evıl.com",  # dotless i: not ASCII
    ],
)
def test_anything_that_could_smuggle_a_host_is_refused(host):
    assert not valid_host(host)


@pytest.mark.parametrize(
    "path",
    ["/api/v2/incidents/{key}.json", "/v1/{key}", "/a/b/c/{key}/d.json"],
)
def test_path_templates_with_one_placeholder_are_accepted(path):
    assert valid_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "api/{key}.json",  # must start at the root
        "/api/{key}/../{key}.json",  # two placeholders
        "/api/../../etc/{key}",  # climbing out
        "/api/{key}?raw=1",  # query strings can change what is served
        "/api/{key}#frag",
        "/api/v2/incidents.json",  # no placeholder at all
        "https://evil.com/{key}",
        "//evil.com/{key}",  # protocol relative
    ],
)
def test_paths_that_could_leave_the_template_are_refused(path):
    assert not valid_path(path)


@pytest.mark.parametrize("key", ["nlxnbqnkdzdl", "abc-123_XYZ", "0"])
def test_plain_keys_are_accepted(key):
    assert valid_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "   ",
        "../secrets",
        "a/b",
        "a.b",  # a dot could reach another document
        "a?b",
        "a b",
        "٣٤",  # Arabic-Indic digits: isalnum() would allow these
        "été",  # accented letters
        "x" * 65,
    ],
)
def test_keys_that_are_not_plain_ascii_are_refused(key):
    assert not valid_key(key)


def test_fields_keep_their_declared_order():
    assert parse_fields("incident.id, incident.created_at ,incident.impact") == [
        "incident.id",
        "incident.created_at",
        "incident.impact",
    ]


@pytest.mark.parametrize(
    "fields",
    ["", "   ", ",,,", "a,a", "a..b", ".a", "a.", "a/b", "a,b,c,d,e,f,g", "x" * 65],
)
def test_bad_field_lists_are_refused(fields):
    with pytest.raises(ValueError):
        parse_fields(fields)


# ----------------------------------------------------------------------
# turning a document into values
# ----------------------------------------------------------------------

DOC = {
    "incident": {
        "id": "nlxnbqnkdzdl",
        "created_at": "2026-09-16T07:20:59.000Z",
        "resolved_at": None,
        "impact": "major",
        "shortlink": 12345,
        "resolved": False,
        "updates": [{"body": "first"}, {"body": "second"}],
        "page": {"nested": {"deep": "value"}},
    }
}


@pytest.mark.parametrize(
    "path,expected",
    [
        ("incident.id", "nlxnbqnkdzdl"),
        ("incident.impact", "major"),
        ("incident.shortlink", "12345"),
        ("incident.resolved", "false"),
        ("incident.page.nested.deep", "value"),
        ("incident.updates.0.body", "first"),
        ("incident.updates.1.body", "second"),
    ],
)
def test_scalars_are_read_at_any_depth(path, expected):
    assert pick(DOC, path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "incident.resolved_at",  # null is absent, not the text "None"
        "incident.missing",
        "missing.entirely",
        "incident.id.deeper",  # a scalar has nothing under it
        "incident.updates.9.body",  # past the end of the list
        "incident.updates.body",  # a list indexed by a name
        "incident.updates",  # a container is not a value
        "incident.page",
    ],
)
def test_anything_that_is_not_a_scalar_reads_as_absent(path):
    assert pick(DOC, path) == ""


def test_a_document_that_holds_none_of_the_fields_is_absent_not_unreadable():
    values, present = extract({"other": 1}, ["incident.id", "incident.impact"])
    assert values == ["", ""]
    assert present is False


def test_one_field_present_is_enough_to_count_as_read():
    values, present = extract(DOC, ["incident.missing", "incident.impact"])
    assert values == ["", "major"]
    assert present is True


def test_values_survive_a_round_trip_in_field_order():
    values = ["nlxnbqnkdzdl", "", "major"]
    assert split_values(join_values(values), 3) == values


def test_a_value_containing_a_newline_is_refused_rather_than_escaped():
    with pytest.raises(ValueError):
        join_values(["fine", "two\nlines"])


def test_a_short_record_pads_rather_than_raising():
    assert split_values("only", 3) == ["only", "", ""]


def test_the_three_statuses_are_distinct():
    assert len({READ, ABSENT, UNREADABLE}) == 3
