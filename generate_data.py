"""Seed the Pulse dashboard with realistic test data."""
import random
import pulse

pulse.init()

USERS = ["alice", "bob", "charlie", "diana", "eve", "frank"]
PAGES = ["/home", "/pricing", "/features", "/docs", "/signup", "/dashboard"]
BUTTONS = ["start_trial", "view_pricing", "contact_us", "read_docs", "upgrade"]
API_ENDPOINTS = ["/api/users", "/api/events", "/api/reports", "/api/settings"]

def page_view(user):
    pulse.track("page_view", user_id=user, properties={"page": random.choice(PAGES)})

def button_click(user):
    pulse.track("button_click", user_id=user, properties={"button": random.choice(BUTTONS)})

def api_request(user):
    pulse.track("api_request", user_id=user, properties={
        "endpoint": random.choice(API_ENDPOINTS),
        "status": random.choices([200, 404, 500], weights=[85, 10, 5])[0],
        "latency_ms": random.randint(20, 400),
    })

def signup(user):
    pulse.track("signup", user_id=user, properties={"plan": random.choice(["free", "pro"])})

def error(user):
    pulse.track("error", user_id=user, properties={
        "message": random.choice(["Unexpected error", "Timeout", "Permission denied"]),
        "code": random.choice([400, 403, 500]),
    })

# Weighted mix of events that reflects realistic usage
event_fns = [
    (page_view,    50),
    (button_click, 25),
    (api_request,  15),
    (signup,        5),
    (error,         5),
]
choices, weights = zip(*event_fns)

print("Sending 200 events to http://localhost:4747 ...")

for _ in range(200):
    user = random.choice(USERS)
    fn = random.choices(choices, weights=weights)[0]
    fn(user)

pulse.flush()
print("Done. Open http://localhost:4747 to see the dashboard.")
