"""
The pure part of SIGNAL. No chain, no network, no model.

Everything here is a total function over strings. A reading that two
validators disagree about is worthless, so every step that turns a fetched
document into a stored value lives in this file, where it can be tested
directly and read by anyone checking what consensus actually compared.

The three statuses are the point of the whole design, and they are three
different claims about the world:

    read        the document was fetched and the field was present
    absent      the document was fetched and the field was not there
    unreadable  the document could not be fetched at all

Collapsing "absent" into "unreadable" is how a leader turns a source that
says nothing into a source that is broken, which is a lie a validator who
fetched the page can catch. They are kept apart on purpose.
"""

READ = "read"
ABSENT = "absent"
UNREADABLE = "unreadable"

# A field path is dotted, like "incident.created_at". Keep the shape narrow:
# anything else is refused when a feed is registered rather than guessed at
# while a reading is being taken.
_MAX_FIELDS = 6
_MAX_PATH = 64
_MAX_KEY = 64


def valid_host(host: str) -> bool:
    """
    A bare hostname: letters, digits, dots and hyphens.

    No scheme, no slash, no port, no credentials. The contract builds the
    URL itself, so anything that could smuggle a second host or a path out
    of this value is refused at registration.
    """
    h = (host or "").strip().lower()
    if not h or len(h) > 100 or h.startswith(".") or h.endswith(".") or ".." in h:
        return False
    for ch in h:
        if not (("0" <= ch <= "9") or ("a" <= ch <= "z") or ch in "-."):
            return False
    return "." in h


def valid_path(path: str) -> bool:
    """
    A path template with exactly one {key} placeholder.

    Refuses anything that could leave the path: no "..", no scheme, no
    query string, and it must start at the root.
    """
    p = (path or "").strip()
    if not p.startswith("/") or len(p) > 200:
        return False
    if ".." in p or "://" in p or "?" in p or "#" in p or "//" in p:
        return False
    return p.count("{key}") == 1


def valid_key(key: str) -> bool:
    """
    The one value a caller supplies that reaches the URL.

    ASCII letters, digits, hyphen and underscore only. `str.isalnum()` alone
    is not enough: it accepts other alphabets, and a key that is not plain
    ASCII cannot be compared byte for byte with what a provider published.
    """
    k = (key or "").strip()
    if not k or len(k) > _MAX_KEY:
        return False
    for ch in k:
        if not (("0" <= ch <= "9") or ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch in "-_"):
            return False
    return True


def valid_field_path(path: str) -> bool:
    """A dotted path, in the same shape a feed may declare."""
    if not path or len(path) > _MAX_PATH:
        return False
    if path.startswith(".") or path.endswith(".") or ".." in path:
        return False
    for ch in path:
        if not (("0" <= ch <= "9") or ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch in "._-"):
            return False
    return True


def parse_fields(fields: str) -> list:
    """
    The declared field paths of a feed, in order, as a list.

    Order is part of the feed: readings store values in the same order, so a
    consumer can name a field and know which value it gets.
    """
    out = []
    for raw in (fields or "").split(","):
        path = raw.strip()
        if not path:
            continue
        if not valid_field_path(path):
            raise ValueError("bad field path: " + repr(path))
        if path in out:
            raise ValueError("duplicate field path: " + repr(path))
        out.append(path)
    if not out:
        raise ValueError("a feed needs at least one field path")
    if len(out) > _MAX_FIELDS:
        raise ValueError(f"at most {_MAX_FIELDS} fields per feed")
    return out


def pick(document, path: str) -> str:
    """
    One value out of a decoded JSON document, by dotted path, as a string.

    Returns "" when the path is not there, which the caller reads as absent.
    A container (list or dict) found at the end of a path counts as absent
    too: storing a nested structure as text invites two validators to format
    it differently and disagree about a document neither of them changed.

    Numbers and booleans are rendered the way Python renders them, which is
    deterministic across validators because the input is already parsed.
    """
    node = document
    for part in path.split("."):
        if isinstance(node, dict):
            if part not in node:
                return ""
            node = node[part]
        elif isinstance(node, list):
            if not part.isdigit():
                return ""
            i = int(part)
            if i >= len(node):
                return ""
            node = node[i]
        else:
            return ""
    if node is None:
        return ""
    if isinstance(node, (dict, list)):
        return ""
    if node is True:
        return "true"
    if node is False:
        return "false"
    return str(node)


def extract(document, paths: list) -> tuple:
    """
    Every declared field of a document, and whether any was present.

    Returns (values, any_present). A document that parsed but held none of
    the declared fields is `absent`, not `unreadable`: it was read, and it
    said nothing.
    """
    values = [pick(document, p) for p in paths]
    return values, any(v != "" for v in values)


def join_values(values: list) -> str:
    """
    Values as one stored string, newline separated, in field order.

    Newlines cannot appear in a value: `pick` only ever returns a scalar
    rendered as text, and a value containing a newline would make the stored
    record ambiguous, so it is refused rather than escaped.
    """
    for v in values:
        if "\n" in v:
            raise ValueError("a value may not contain a newline")
    return "\n".join(values)


def split_values(blob: str, count: int) -> list:
    """The inverse of join_values, padded so a reader always gets `count`."""
    parts = (blob or "").split("\n") if blob else []
    while len(parts) < count:
        parts.append("")
    return parts[:count]
