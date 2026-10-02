// A live SIGNAL, one step per run, so every result is checked before the next.
//
//   npm install
//   export GENLAYER_KEYSTORE=~/.genlayer/keystores/mykey.json
//   export GENLAYER_PASSWORD=...           # never stored in this repo
//
//   node deploy/demo.mjs show
//   node deploy/demo.mjs register <name> <host> <path-template> <fields>
//   node deploy/demo.mjs read     <feed_id> <key>
//
// The address comes from live.json, written by deploy/deploy.mjs.
//
// Quote the path template: it contains braces, and a shell that rewrites
// POSIX paths will turn "/api/v2/..." into something else entirely. One
// registration was refused on chain for exactly that.
import { readFileSync } from "node:fs";
import { balance, connect, estimateFees, fmt, txUrl, waitFor } from "./chain.mjs";

const live = JSON.parse(readFileSync(new URL("./live.json", import.meta.url), "utf8"));
const SIGNAL = live.signal;
if (!SIGNAL) throw new Error("deploy/live.json has no address yet");

const { account, client } = await connect();

const view = (fn, args = []) => client.readContract({ address: SIGNAL, functionName: fn, args });

async function write(functionName, args) {
  const fees = await estimateFees(client, { address: SIGNAL, functionName, args, value: 0n });
  const txId = await client.writeContract({
    address: SIGNAL,
    functionName,
    args,
    value: 0n,
    // A reading is one web fetch per validator, and a rotation costs a round.
    consensusMaxRotations: 8,
    ...(fees ? { fees } : {}),
  });
  const receipt = await waitFor(client, txId);
  console.log("  ", txUrl(txId));
  if (!receipt.ok) console.log("   returned nothing:", receipt.outcome);
  return receipt;
}

const [step, ...rest] = process.argv.slice(2);
console.log("wallet", account.address, fmt(await balance(account.address)), "\n");

if (step === "register") {
  const [name, host, path, fields] = rest;
  await write("register", [name, host, path, fields]);
} else if (step === "read") {
  const [feed, key] = rest;
  await write("read", [feed, key]);
  console.log("stored", JSON.stringify(await view("get_reading", [feed, key])));
} else if (step !== "show") {
  console.log("steps: show, register, read");
  process.exit(1);
}

console.log("");
for (const id of await view("feed_list")) {
  const feed = await view("get_feed", [id]);
  console.log("feed", id, "->", feed.example_url);
}
