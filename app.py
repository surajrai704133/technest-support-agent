"""TechNest autonomous support agent: L1 -> L2 -> L3 escalation loop.
Run: pip install flask anthropic ; export ANTHROPIC_API_KEY=...(optional) ; python app.py
Without an API key it uses a built-in rule engine, so it always works."""
import os, json, uuid
from flask import Flask, request, jsonify

try:
    import anthropic
    client = anthropic.Anthropic() if os.getenv("ANTHROPIC_API_KEY") else None
except ImportError:
    client = None
MODEL = "claude-sonnet-4-6"

STAFF = {1: ("Rohan Mehta", "Sales Executive"),
         2: ("Priya Sharma", "Store Manager"),
         3: ("Vikram Desai", "Regional Manager")}
POWERS_TEXT = {
 1: "Refund <=Rs1000 within 7 days; replace accessories within 7 days; book repair ticket; goodwill gift.",
 2: "Refund/replace <=Rs15000 within 15 days; waive repair charges <=Rs3000; coupon <=20%; priority repair; plus all L1 powers.",
 3: "Unlimited refund/replace, may override return policy, compensation, final decision. No escalation beyond you."}

def validate(level, c, o):
    """Hard guardrail in CODE: the AI cannot exceed a role's power."""
    t, amt, d, price = o["type"], o.get("amount", 0), c["days"], c["price"]
    if level == 3: return True, ""
    if t == "goodwill": return True, ""
    if t == "repair": return (True, "") if level == 1 or amt <= 3000 else (False, "waiver > Rs3000")
    if t == "coupon": return (True, "") if level >= 2 and amt <= 20 else (False, "coupon needs L2 and <=20%")
    lim, days = (1000, 7) if level == 1 else (15000, 15)
    if t == "replace" and level == 1 and c["category"] != "accessory":
        return False, "L1 replaces accessories only"
    if t in ("refund", "replace"):
        if price > lim: return False, f"amount Rs{price} exceeds limit Rs{lim}"
        if d > days: return False, f"{d} days exceeds {days}-day window"
        return True, ""
    return False, "unknown offer type"

TOOLS = [
 {"name": "make_offer", "description": "Propose a resolution to the customer within your power.",
  "input_schema": {"type": "object", "properties": {
     "type": {"type": "string", "enum": ["refund", "replace", "repair", "goodwill", "coupon"]},
     "amount": {"type": "number", "description": "Rs waived for repair, % for coupon, else 0"},
     "message": {"type": "string", "description": "Friendly message to the customer"}},
   "required": ["type", "message"]}},
 {"name": "escalate", "description": "Pass the case to your senior if nothing within your power can resolve it.",
  "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}]

def rule_decide(c, level):
    """Fallback brain (no LLM)."""
    pref = {"refund": ["refund", "replace", "repair", "coupon", "goodwill"],
            "replace": ["replace", "refund", "repair", "coupon", "goodwill"],
            "repair": ["repair", "replace", "refund", "coupon", "goodwill"]}.get(c["desired"], ["repair", "goodwill"])
    for t in pref:
        if t in c["rejected"]: continue
        o = {"type": t, "amount": {"coupon": 10, "repair": 0}.get(t, 0)}
        ok, _ = validate(level, c, o)
        if ok:
            o["message"] = f"I'm offering a {t} for your {c['product']}."
            return "offer", o
    return "escalate", {"reason": "No allowed option satisfies the request at my level."}

def llm_decide(c, level):
    name, post = STAFF[level]
    system = (f"You are {name}, {post} at TechNest Electronics. Your powers: {POWERS_TEXT[level]} "
              "Resolve the complaint by calling make_offer (within your powers) or escalate. "
              f"Never repeat rejected offer types: {c['rejected']}. Be brief and polite.")
    case = {k: c[k] for k in ("product", "category", "price", "days", "problem", "desired")}
    msgs = [{"role": "user", "content": json.dumps(case)}]
    for _ in range(3):
        r = client.messages.create(model=MODEL, max_tokens=500, system=system, tools=TOOLS,
                                   tool_choice={"type": "any"}, messages=msgs)
        tu = next(b for b in r.content if b.type == "tool_use")
        if tu.name == "escalate": return "escalate", tu.input
        ok, why = validate(level, c, tu.input)
        if ok and tu.input["type"] not in c["rejected"]: return "offer", tu.input
        msgs += [{"role": "assistant", "content": r.content},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu.id,
                  "is_error": True, "content": f"Rejected: {why or 'already rejected'}. Choose another or escalate."}]}]
    return "escalate", {"reason": "Could not find a valid action."}

def decide(c, level):
    if client:
        try: return llm_decide(c, level)
        except Exception as e: c["log"].append(f"[LLM error, using rules: {e}]")
    return rule_decide(c, level)

def run_agent(c):
    """The autonomous loop: runs until an offer is on the table or the case is closed."""
    while True:
        lvl = c["level"]; name, post = STAFF[lvl]
        kind, data = decide(c, lvl)
        if kind == "offer":
            c["offer"] = data; c["status"] = "awaiting_customer"
            c["log"].append(f"L{lvl} {name} ({post}) offers {data['type']}: {data['message']}")
            return
        c["log"].append(f"L{lvl} {name} ({post}) escalates: {data['reason']}")
        if lvl == 3:
            c["status"] = "closed_unresolved"; c["offer"] = None
            c["log"].append("L3 final decision: no further options. Case closed with explanation.")
            return
        c["level"] += 1

import atexit
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.json")
CASES = json.load(open(DB)) if os.path.exists(DB) else {}
def save(): json.dump(CASES, open(DB, "w"))
atexit.register(save)
app = Flask(__name__)

@app.post("/api/complain")
def complain():
    j = request.json
    c = dict(id=uuid.uuid4().hex[:6], name=j["name"], product=j["product"], category=j["category"],
             price=float(j["price"]), days=int(j["days"]), problem=j["problem"], desired=j["desired"],
             level=1, rejected=[], offer=None, status="processing", log=[])
    CASES[c["id"]] = c; run_agent(c); save(); return jsonify(c)

@app.get("/api/case/<cid>")
def get_case(cid):
    return (jsonify(CASES[cid]), 200) if cid in CASES else (jsonify(error="not found"), 404)

@app.post("/api/respond/<cid>")
def respond(cid):
    c = CASES[cid]
    if c["status"] != "awaiting_customer": return jsonify(c)
    if request.json["accept"]:
        c["status"] = "resolved"; c["log"].append("Customer accepted. Case RESOLVED.")
    else:
        c["rejected"].append(c["offer"]["type"]); c["log"].append("Customer rejected the offer.")
        if c["level"] < 3: c["level"] += 1
        run_agent(c)
    save(); return jsonify(c)

PAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

@app.get("/")
def home(): return open(PAGE_FILE, encoding="utf-8").read()

if __name__ == "__main__":
    print("LLM mode" if client else "Rule-engine mode (set ANTHROPIC_API_KEY for LLM)")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
