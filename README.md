# TechNest Autonomous Support Agent

An agentic AI customer-support system. A customer reports a problem, and an AI agent works through a 3-level authority hierarchy, escalating until the case is resolved or a final decision is made.

## How it works

1. The customer submits a complaint from the dashboard.
2. The agent starts at **Level 1** and either makes an offer within that role's power or escalates.
3. The customer accepts (case resolved) or rejects (case escalates to the next level with full history).
4. **Level 3 is final.** If no options remain, the case closes with an explanation.

| Level | Role | Authority |
|---|---|---|
| L1 | Sales Executive | Refund up to Rs 1,000 within 7 days, accessory replacement, repair ticket, goodwill gift |
| L2 | Store Manager | Refund/replace up to Rs 15,000 within 15 days, repair waiver up to Rs 3,000, coupon up to 20% |
| L3 | Regional Manager | No amount limit, policy override, final decision |

## Key design points

- **LLM tool calling:** the model chooses between `make_offer` and `escalate` each step.
- **Code-enforced guardrails:** `validate()` blocks any offer beyond a role's power; the model gets an error and must choose again.
- **Rule-based fallback:** without an API key (or if the API fails) a built-in rule engine makes the decisions, so the app always works.
- **One dashboard, two modes:** `dashboard.html` uses the Flask API when a backend exists, otherwise runs fully in the browser.

## Project structure

```
app.py            Flask server, agent loop, guardrails, REST API
dashboard.html    Customer dashboard (served at /)
requirements.txt  Python dependencies
render.yaml       Render deployment config
```

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key   # optional; omit for rule-engine mode
python app.py
```

Open http://localhost:5000. On Windows PowerShell use `$env:ANTHROPIC_API_KEY="your_key"`.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/complain` | Create a case and run the agent |
| GET | `/api/case/<id>` | Get one case |
| POST | `/api/respond/<id>` | Body `{"accept": true/false}` |

## Deploy on Render

Push this repo to GitHub, then in Render choose **New > Blueprint**, select the repo and apply. Add `ANTHROPIC_API_KEY` as an environment variable for LLM mode (optional).

## Limitations

- Cases are stored in a local `cases.json`; it resets on free-tier restarts.
- No customer login yet; the browser remembers its own case IDs.
- Possible next steps: database storage, staff dashboard, inventory and warranty tools.

Built with Python, Flask, the Anthropic API, and vanilla HTML/CSS/JavaScript.
