"""
A stand-in SIGNAL, for testing a contract that consumes one.

Direct mode loads one contract per process, so a consumer cannot be tested
against the real SIGNAL in the same test. This answers the cross-contract
call with the protocol the chain actually uses, which means the consumer
really does call out and the reply really is calldata encoded.

What a stub buys is states that are tedious to produce for real: a reading
that is stale, absent, unreadable, or simply never taken.
"""

FEED = "0xaa:github"
KEY = "zkxwbgr0cnmx"
FIELDS = ["incident.id", "incident.impact", "incident.status"]

# A real GitHub incident: critical, opened and resolved on 2026-08-17.
VALUES = {"incident.id": KEY, "incident.impact": "critical", "incident.status": "resolved"}

EARLIER = "2026-09-30T09:00:00Z"
OPENED = "2026-10-01T09:00:00Z"
LATER = "2026-10-02T09:00:00Z"

# StorageView. A reading that is merely decided can still be rolled back, so
# a consumer that moves value should be asking for 1.
VIEW_DEFAULT, VIEW_LATEST_FINALIZED, VIEW_LATEST_DECIDED = 0, 1, 2


class SignalStub:
    """Answers `get_reading` and `get_feed`, and records how it was asked."""

    def __init__(self):
        self.fields = list(FIELDS)
        self.reading = {
            "feed": FEED,
            "key": KEY,
            "status": "read",
            "values": dict(VALUES),
            "url": "https://www.githubstatus.com/api/v2/incidents/" + KEY + ".json",
            "read_at": LATER,
        }
        self.views = []

    def set_reading(self, **changes):
        self.reading = {**self.reading, **changes}

    def install(self, vm):
        def hook(_vm, request):
            # Imported here rather than at install time: the SDK only exists
            # once a contract has been loaded, and the stub is installed first.
            from gltest.direct.sdk_compat import import_calldata

            calldata = import_calldata()

            if "CallContract" not in request:
                return None
            call = request["CallContract"]
            method = call["calldata"][""]
            self.views.append({"method": method, "storage_view": call.get("storage_view")})
            if method == "get_feed":
                answer = {
                    "feed_id": FEED,
                    "host": "www.githubstatus.com",
                    "path": "/api/v2/incidents/{key}.json",
                    "fields": self.fields,
                    "creator": "0x" + "aa" * 20,
                    "registered_at": EARLIER,
                    "example_url": "https://www.githubstatus.com/api/v2/incidents/{key}.json",
                }
            else:
                answer = self.reading
            return bytes([0]) + calldata.encode(answer)

        vm._gl_call_hook = hook
        return self
