"""First-setup helper: give THIS repo copy its own random uuid.
Runs on GitHub Actions (publish.yml) right after 'Use this template'.
Safe: static file edit only, no proxy, no tunnel, no cron."""
import json, uuid

TEMPLATE_UUID = "9ec8f3be-758e-487f-b057-cb1e1ddf4a9b"
P = "singbox-server.json"

d = json.load(open(P, encoding="utf-8"))
cur = d["inbounds"][0]["users"][0].get("uuid", "")
if cur in ("", TEMPLATE_UUID):
    new = str(uuid.uuid4())
    d["inbounds"][0]["users"][0]["uuid"] = new
    json.dump(d, open(P, "w", encoding="utf-8"), indent=2)
    print("fresh uuid:", new)
else:
    print("keeping existing uuid")
