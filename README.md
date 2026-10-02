# SIGNAL

An attested reader for GenLayer. A web fact that every validator fetched for itself, stored on chain with a status that says which kind of fact it is.

A contract that needs something from the web has three problems. It cannot let the caller supply the URL, because whoever names the document has appointed themselves the judge. It cannot store whatever the leader saw, because a leader that lies is the whole threat model. And it cannot treat "the page said nothing" and "the page could not be read" as the same thing, because one of those is a claim about the world and the other is a claim about the network.

SIGNAL solves those three once so a consumer contract does not have to solve them again.

```
register(name, host, path, fields)   fix a source, immutably
read(feed_id, key)                   take a reading under consensus
get_reading(feed_id, key)            what consensus agreed, as a free view
value_of(feed_id, key, field)        one field of it, as text
```

No model is involved anywhere. Validators fetch a document and compare strings.

| | |
|---|---|
| Contract | [`0xb4EA63892D4F8eA3D552486541CE4Deb6Db596BC`](https://explorer-studio-dev.genlayer.com/address/0xb4EA63892D4F8eA3D552486541CE4Deb6Db596BC) |
| Network | GenLayer Studio Next, chain id 61997, `https://studio-next.genlayer.com/api` |
| Engine | Consensus v0.6, GenVM v0.3, runner `py-genlayer:5jycge...` |
| Tests | 128, `python -m pytest -q` |
| Deployed source | byte-identical to [`contracts/signal_bundle.py`](contracts/signal_bundle.py), sha256 `8f74fb87...`, checked by `node deploy/verify.mjs` |
| A contract that uses it | [WARRANT](https://github.com/Jennivarl/Warrant), which pays out on a reading |

---

## The three statuses are the whole design

Most oracles have two outcomes: a value, or a failure. That collapse is where the attack lives, because it lets a leader turn a source that said nothing into a source that was broken, and nobody downstream can tell the difference.

| status | what happened | values stored | may a consumer act on it |
|---|---|---|---|
| `read` | the document was fetched and at least one declared field was present | every declared field | yes |
| `absent` | the document was fetched and held none of the declared fields, or the source answered 404 | all empty | no: the source answered, and it said nothing |
| `unreadable` | the document could not be fetched, or was not JSON, or the server errored | none | no: this says nothing about the world, only about the attempt |

A reading that was never taken is a fourth case, and it reads back as status `""` rather than as an invented record.

The distinction is enforced on both sides of consensus. A validator that read the document will not agree that it was unreadable. A validator that could not read it will not attest to any value, however plausible.

---

## What consensus derived, and what was copied

Every field stored by a reading is derived independently by every validator. Nothing is taken on the leader's word.

| stored field | where it comes from | derived or copied |
|---|---|---|
| `status` | each validator fetched the document itself and classified its own response | derived |
| `values` | each validator extracted the declared fields from its own copy | derived |
| `url` | built by the contract from the registered host and path plus the key | derived |
| `read_at` | the transaction's own `datetime`, part of the message every validator sees | derived |
| `feed`, `key` | the call arguments, echoed, and `url` shows what they built | derived |

The leader's result is used for one thing only: as the proposal a validator checks against its own. If they differ in any declared field, the validator disagrees.

Validators compare **only the declared fields**, never the whole response. A status page carries fields that move between requests, and comparing the raw body would make every honest validator disagree about a document that did not change.

---

## What a dishonest leader can try

Each of these is a lie a leader would have an actual reason to tell, and each is a test that runs on every commit.

| the lie | why it would be worth telling | what happens | test |
|---|---|---|---|
| call a working page broken | blocks a payout that is owed | rejected: the validator read it | `test_a_validator_rejects_a_leader_who_hides_a_readable_record` |
| change a value | pays the wrong side | rejected: field by field comparison | `test_a_validator_rejects_a_leader_who_changes_a_value` |
| move a timestamp | shifts an event into or out of a window | rejected | `test_a_validator_rejects_a_leader_who_moves_a_timestamp` |
| call a present record absent | makes a real event disappear | rejected | `test_a_validator_rejects_a_leader_who_calls_a_present_record_absent` |
| invent a record for a key that 404s | manufactures an event | rejected: the page 404s for the validator too | `test_a_validator_rejects_a_leader_who_invents_a_record_for_a_missing_key` |
| crash instead of answering | stalls the round | rejected: a malformed result is a disagreement, not an exception | `test_a_validator_rejects_a_leader_that_errored` |
| claim a value while the source is down | invents a fact out of an outage | rejected: a validator that cannot read agrees only to `unreadable` | `test_a_validator_that_cannot_read_agrees_only_that_it_could_not_be_read` |

The last row is the one that matters most. Honest disagreement about an outage is safe. Agreeing to a value nobody could read is not.

---

## A source cannot be moved under a consumer

A feed id carries the address that registered it: `0xb428...a75a:github`. Nobody can squat the name `github`, and a consumer can always see whose source it is about to trust.

Once registered a feed never changes. The host, the path template and the declared fields are fixed, so the document a reading points at cannot be redirected after a consumer has come to depend on it. Registering the same name twice is refused rather than treated as an edit.

The only thing a caller contributes to a reading is the key, and that is checked (ASCII letters, digits, hyphen, underscore) and then written into the record, so anyone can see what was asked for. A host must be a bare hostname with no scheme, port or path. A path template must start at `/`, contain `{key}` exactly once, and carry no `..`, no `//`, no query and no fragment. Everything else is refused when the feed is registered, while the registrar can still fix it, rather than at read time when it would quietly mean "never works".

---

## Verified live on Studio Next

Every row is a real transaction against the contract above. The contract is immutable, so all of it can be re-read at any time.

| step | transaction | outcome |
|---|---|---|
| Deploy | [`0xb74ca39f...`](https://explorer-studio-dev.genlayer.com/tx/0xb74ca39fb090864ac310fe0bf362c818b255846a061e2ab8b2e8681dee0512a8) | contract live, and its source is byte-identical to the bundle in this repo |
| Register the GitHub status feed | [`0xb883f58b...`](https://explorer-studio-dev.genlayer.com/tx/0xb883f58b3d14ff16484a3d415206072d3faf66c0b3826dd9503cacab9490bed1) | feed `0xb428...a75a:github`, five declared fields, immutable |
| Register the npm registry as a second feed | [`0x269cba4f...`](https://explorer-studio-dev.genlayer.com/tx/0x269cba4fee84153f277794344f2f8d0ff1dfba1687a2d206e49806c24077c264) | another host, another document shape, no change to the contract |
| Register an HTML page as a third feed | [`0x8ed3f1ac...`](https://explorer-studio-dev.genlayer.com/tx/0x8ed3f1ac459c7f48712e0471754a8f900c97b84e300edac54d02ed6dc1071228) | registered so the `unreadable` path can be shown on a real page |
| Register a host with a scheme in it | [`0x9b5c6b53...`](https://explorer-studio-dev.genlayer.com/tx/0x9b5c6b53d8c17f0bdd009be9397758f715333950860c5285d5877cca6c31fa5f) | **refused**, `host must be a bare hostname, with no scheme, port or path`. Validators agreed on the refusal and the feed list stayed at three |
| Read a real incident | [`0xaba4b8ca...`](https://explorer-studio-dev.genlayer.com/tx/0xaba4b8caff59296b783f3af23099e13768fa0cb89aae614646c00338ced28ce0) | **`read`**: `critical`, `resolved`, opened 13:40:03 and resolved 21:15:46 on 17 Aug. Every validator fetched githubstatus.com and agreed on all five fields |
| Read a key that does not exist | [`0x02eb0aca...`](https://explorer-studio-dev.genlayer.com/tx/0x02eb0aca46f1e78e213e7b2cc0628c7e55ef9efd4bf0e37879e0e310dea77b6f) | **`absent`**, every value empty. The source answered 404, which is an answer |
| Read a package | [`0x70705f61...`](https://explorer-studio-dev.genlayer.com/tx/0x70705f611d2fe2cac25b156b7a4a259f5e407e7dfd69934e9d7dbd460f04ca7f) | **`read`**: `dist-tags.latest` 1.1.8, `maintainers.0.name` jmlago, `license` MIT. A field under a hyphenated key and a field reached through a list index |
| Read an HTML page | [`0x2567633b...`](https://explorer-studio-dev.genlayer.com/tx/0x2567633bb726f35179e803e32be4634dbb864cac5cadf041f7cb197195d9b86f) | **`unreadable`**: the page returned 200 and was not JSON. No values stored |
| Read the incident again | [`0x872aaa90...`](https://explorer-studio-dev.genlayer.com/tx/0x872aaa904ce052c77afaa1e484fd68b9ed626d52226414f70f46270c63e0e5c5) | latest wins, `read_at` moves to 16:07:58Z. The record is overwritten rather than appended, so a feed read hourly does not grow without bound |

The GitHub feed reads `https://www.githubstatus.com/api/v2/incidents/{key}.json`, the npm feed reads `https://registry.npmjs.org/{key}`, and a reading stores the URL it built, so none of this has to be taken on trust.

[WARRANT](https://github.com/Jennivarl/Warrant) then paid out 1 GEN against that last reading, to a wallet that held nothing: [`0x66cbc8d1...`](https://explorer-studio-dev.genlayer.com/tx/0x66cbc8d1648520710ccb4a9c8ff5db6ae552c448434289be821ae6b8f1e73b8d). That is the point of having a reader at all. Money moved because every validator fetched the same document and agreed, and nobody had to be trusted to report it.

---

## Checking that the live contract runs this code

The deploy transaction carries the contract's source, so this needs no trust in the address, the explorer or this README:

```sh
node deploy/verify.mjs
```

```
contract       0xb4EA63892D4F8eA3D552486541CE4Deb6Db596BC
deploy tx      0xb74ca39fb090864ac310fe0bf362c818b255846a061e2ab8b2e8681dee0512a8
on chain       9414 bytes, sha256 8f74fb8759b74e750bccbe5ece2b3ec301180d7abf51e7ec8ad0c13d5bfa35a6
in this repo   9414 bytes, sha256 8f74fb8759b74e750bccbe5ece2b3ec301180d7abf51e7ec8ad0c13d5bfa35a6

IDENTICAL
```

---

## Using it from another contract

[`examples/consumer.py`](examples/consumer.py) is the whole pattern, and it is deployed and run by its own tests rather than left as prose.

```python
record = gl.contract.get_at(self.signal).view().get_reading(feed_id, key)
if str(record["status"]) != "read":
    return {"acted": False, "why": "no attested reading yet"}
if str(record["read_at"]) <= self.since:
    return {"acted": False, "why": "that reading predates this contract"}
return {"acted": True, "value": str(record["values"][field])}
```

Two checks, and both matter. Test for `read` by name rather than for "not an error", so that a status added later cannot quietly become a reason to act. And compare `read_at` against your own commitment, because a reading taken before you existed says nothing about you.

`get_reading` and `value_of` are views, so reading costs nothing and needs no wallet.

---

## The storage view, and why this reads the default one

Asking for `StorageView.LATEST_FINALIZED` is the natural way to refuse a reading that consensus could still roll back. That read times out on Studio Next.

Shown with a throwaway probe contract whose two methods differ in nothing but the storage view, reading the same key of the same SIGNAL contract with the same arguments:

| view | transaction | result |
|---|---|---|
| default | [`0x5c6dcfe2...`](https://explorer-studio-dev.genlayer.com/tx/0x5c6dcfe234f7c26141e14867b6b2902059a563ae90494ff7f1ba1a4de39f41cc) | `FINISHED_WITH_RETURN` |
| `LATEST_FINALIZED` | [`0x1aaccb97...`](https://explorer-studio-dev.genlayer.com/tx/0x1aaccb970988179aefcf40bac205fc8561316beaa69caa3d0de88ed95ed2513c) | `TIMEOUT` |

So a consumer reads the default view. For a contract that only reads, that is fine. A contract that moves money on a reading has to cover the rollback window some other way, and [WARRANT](https://github.com/Jennivarl/Warrant) does it with elapsed time: it pays only on a reading that has existed for an hour.

---

## Limits, stated plainly

- **A feed is only as honest as its source.** SIGNAL proves that every validator saw the same document at the same URL. It cannot prove the publisher told the truth. Choosing a source is the registrar's judgement, and the feed id names who made it.
- **JSON only.** A document that is not JSON is `unreadable`. There is no HTML scraping, because two validators parsing HTML a week apart is a disagreement waiting to happen.
- **Scalars only.** A declared path that lands on an object or a list reads as absent. Storing a nested structure as text invites two validators to format it differently and disagree about a document neither of them changed.
- **Six fields per feed, 64 characters per path.** Storage is paid for, and a reading is meant to be the few fields a decision turns on.
- **Ordering comparisons are integer only**, and that lives in the consumer rather than here. SIGNAL stores text exactly as the document rendered it.
- **A value containing a newline makes the document `unreadable`.** Values are stored newline separated, and escaping would be another place for two validators to differ.
- **Anyone may refresh a reading**, including while a source happens to be down. That can delay a consumer, never redirect one: a consumer decides on `status` and `read_at`, and taking a fresh reading is equally open to whoever is waiting on it.
- **Readings are latest-wins, not a history.** A consumer that needs the value as of a particular moment should record it when it sees it.
- **Day granularity nowhere.** `read_at` is a full timestamp. Time arithmetic on it belongs to the consumer.

---

## Running it

```sh
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python -m deploy.build_bundle          # contracts/signal_bundle.py, the file that deploys
python -m pytest -q                    # 128 tests, no chain and no network
```

The tests run the contract in genlayer-test's direct mode, in process. There is no node to start. The feed's host is answered by a real GitHub incident record and a real npm metadata document saved under `test/fixtures/`, so the document a test reads is one the provider actually served.

Half of the SIGNAL tests run the validator side rather than the leader side, because a leader that reaches the right answer proves nothing. What matters is whether an honest validator would agree, and whether a dishonest one would be caught.

To deploy and drive a live copy:

```sh
npm install
export GENLAYER_KEYSTORE=~/.genlayer/keystores/mykey.json
export GENLAYER_PASSWORD=...
node deploy/deploy.mjs contracts/signal_bundle.py
node deploy/demo.mjs register github www.githubstatus.com '/api/v2/incidents/{key}.json' 'incident.id,incident.impact,incident.status'
node deploy/demo.mjs read <feed_id> <incident_id>
```

Addresses live in [`deploy/live.json`](deploy/live.json). The password is read from the environment and is never stored in this repo.

---

## Layout

```
contracts/reading.py        the pure part: validation, extraction, encoding. No chain, no network
contracts/signal.py         the contract
contracts/signal_bundle.py  the two pasted together, which is what deploys. Generated
examples/consumer.py        how another contract uses a reading. Deployed by its own tests
deploy/build_bundle.py      builds the bundle; a test fails if the committed one is stale
deploy/chain.mjs            network and signing, in one place
deploy/deploy.mjs           deploy one bundle
deploy/demo.mjs             register and read against a live copy
deploy/verify.mjs           prove the live contract runs this exact bundle
test/                       128 tests
```

GenVM loads a single source file with no access to siblings, so the bundle exists to paste the modules together. Comments and docstrings are stripped from the deployed copy, because a deploy costs gas per byte and a bundle over the cap returns a transaction hash and then simply does not exist. Edit the modules, never the bundle: a test regenerates it and fails if the committed copy has drifted.

## License

MIT
