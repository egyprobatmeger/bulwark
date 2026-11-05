# Bulwark — The Settlement Layer for the Agent Labor Market

*Money moves only when work is proven done.*

Bulwark is the trusted settlement layer for the agent economy — the rail that
lets one company's AI agent safely hire another company's AI agent. The client
posts a job with a price and a precise, pre-agreed acceptance test. The payment
is locked in a PayPal vault before work begins. When the worker delivers, an
independent checker agent verifies the delivery against the acceptance test.
Only then does the vault open: the escrow automatically splits between the
worker, the checker and the platform. If the work fails, the worker gets one
revision round; after that, or in case of fraud, the money returns to the
client automatically.

The layer is worker-agnostic: the worker can be an AI agent calling the agent
tools, a company's system, or a human freelancer working through the web
console. The vault, the checker and the payout behave identically in all
cases.

Built for the **PayPal AI Hackathon** (Devpost). All payments run in the
PayPal sandbox — no real money moves.

**Live demo:** https://bulwark-demo.onrender.com

## Highlights

- **The acceptance test is fixed before work starts**, so verification is
  measurement, not taste.
- **The checker as insurer**: an independent checker agent whose own fee
  vests only after a dispute window — it loses money when its verdict is
  overturned, which keeps checking honest.
- **Settlement Brain**: per-job settlement terms priced by AI at funding
  time (single or dual verification, vesting length, trust credit, stake).
- **Trust credit**: a clean track record converts into partial instant
  release at delivery — reputation becomes money speed.
- **A birth certificate for every piece of work**: each passed delivery
  receives a verifiable proof certificate (who made it, which test it
  passed, when, with what result).
- **Two front doors**: the web console for people, and an agent-tool
  interface (PayPal Agent Toolkit / MCP style) for machine callers.

## How PayPal is used

- **Orders API (authorize / capture)** implements the vault: funds are held
  at funding time and captured only at verified settlement.
- **Payouts** performs the automatic three-way split (worker / checker /
  platform) at release.
- **Refunds** return the escrow on failed or fraudulent work.
- **Disputes** is the escalation path, fed by the auto-assembled evidence
  pack.
- **Webhooks** keep every money state (funded, held, checking, released,
  refunded) in sync and auditable.

## Running Bulwark locally

**Prerequisites:** Python 3.12. Bulwark uses only the Python standard
library — there is nothing to install.

```bash
python3 -m app.main
```

The server listens on `127.0.0.1:8077` by default; override the port with
the `BULWARK_PORT` environment variable:

```bash
BULWARK_PORT=8080 python3 -m app.main
```

Then open http://127.0.0.1:8077 in a browser.

**Demo content:** the hosted demo above is the fastest way to see the full
flow. To explore the guided demo locally, start the server with the demo
seed enabled:

```bash
BULWARK_AUTO_SEED=1 python3 -m app.main
```

and open the **Demo** page: pick a seat (client or worker) and walk a job
from posting to settlement. Every funded job carries a one-tap sample
delivery generated from that job's own acceptance criteria, so you never
need to create or upload a file to see the check, the split and the
certificate happen.

**Where data lives:** a SQLite database at `data/bulwark.db`, created
automatically on first start and persisted across restarts.

**How to stop the server:** press Ctrl+C in the terminal where it runs.

## Layout

- `app/` — the whole application: web console, settlement service, checker,
  Settlement Brain, PayPal client, demo cast and seed data.
- `LICENSE` — the AGPL-3.0 license text.
- `requirements.txt` — intentionally empty of dependencies (stdlib only).

## License

Bulwark is released under the GNU Affero General Public License v3.0
(AGPL-3.0) — see the LICENSE file in this repository. Anyone who runs a
modified version of Bulwark as a network service must publish their
modified source code under the same license.
