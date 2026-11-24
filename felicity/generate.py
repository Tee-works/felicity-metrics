"""Synthetic data generator.

SYNTHETIC DATA ONLY. Agencies, branches, people, phone numbers and addresses are
invented. Phone numbers use the Ofcom drama range (07700 900xxx) and emails use
example.com. Nothing here comes from LightWork or any real agency.

The generator plants known defects so the data quality checks have something to find:
  1. duplicate CRM leads (a webhook firing twice)
  2. BST/GMT errors (a legacy SMS gateway writes UK local time and labels it UTC)
  3. orphan messages and outcomes (their conversation row never arrived)
  4. PII in free text (message bodies, CRM notes)
  5. duplicate message rows (ingest retries)
  6. a stale CRM feed (Street stops syncing on 12 Nov)

It also writes data/truth/, which is never loaded into the warehouse. It holds
the planted rubric labels for the conversation-quality sample.
"""
import csv
import math
import random
from datetime import date, datetime, time, timedelta

from . import config

AGENCIES = [
    # agency_id, name, crm_system, [(branch_id, branch_name, postcode_area, hours_profile)]
    ("AG01", "Harbour & Finch Lettings", "alto", [("BR01", "Cambridge", "CB", "std"), ("BR02", "Ely", "CB", "std"), ("BR03", "Newmarket", "CB", "late")]),
    ("AG02", "Meadowgate Estates", "street", [("BR04", "Leeds Central", "LS", "std"), ("BR05", "Headingley", "LS", "sat_long")]),
    ("AG03", "Northcote Residential", "mri", [("BR06", "Manchester", "M", "late"), ("BR07", "Salford", "M", "std"), ("BR08", "Stockport", "SK", "std")]),
    ("AG04", "Kestrel Property Co", "loop", [("BR09", "Bristol", "BS", "std"), ("BR10", "Bath", "BA", "sat_long")]),
    ("AG05", "Bramley Hart", "alto", [("BR11", "Guildford", "GU", "std"), ("BR12", "Woking", "GU", "std")]),
    ("AG06", "Willowbank Homes", "mri", [("BR13", "Nottingham", "NG", "std"), ("BR14", "Derby", "DE", "late")]),
]

HOURS_PROFILES = {
    # isodow -> (open, close) local; missing day = closed
    "std": {1: ("09:00", "17:30"), 2: ("09:00", "17:30"), 3: ("09:00", "17:30"), 4: ("09:00", "17:30"), 5: ("09:00", "17:30"), 6: ("09:00", "13:00")},
    "late": {1: ("08:30", "18:00"), 2: ("08:30", "18:00"), 3: ("08:30", "18:00"), 4: ("08:30", "18:00"), 5: ("08:30", "18:00"), 6: ("09:00", "14:00")},
    "sat_long": {1: ("09:00", "17:30"), 2: ("09:00", "17:30"), 3: ("09:00", "17:30"), 4: ("09:00", "17:30"), 5: ("09:00", "17:30"), 6: ("10:00", "16:00")},
}

# England and Wales bank holidays, 2026
BANK_HOLIDAYS = [date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 4), date(2026, 5, 25),
                 date(2026, 8, 31), date(2026, 12, 25), date(2026, 12, 28)]

CHANNELS = [("call", 0.35), ("email", 0.22), ("whatsapp", 0.16), ("portal", 0.15), ("sms", 0.12)]
ENQUIRIES = [("lettings", 0.40), ("sales", 0.20), ("valuation", 0.10), ("maintenance", 0.20), ("general", 0.10)]

WEEKDAY_HOURS = [1, .6, .4, .3, .3, .5, 1.2, 2.5, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5.5, 6.5, 7, 6, 5, 3.5, 2]
WEEKEND_HOURS = [1.5, .8, .5, .3, .3, .4, .8, 1.5, 3, 4.5, 5, 5, 5, 5, 4.5, 4.5, 4, 4, 4, 4, 4, 3.5, 3, 2]

# Felicity first-reply latency, lognormal(mu, sigma) in seconds
LATENCY = {"call": (1.2, 0.4), "whatsapp": (2.5, 0.6), "sms": (2.7, 0.6), "email": (4.5, 0.8), "portal": (5.8, 0.9)}

FIRST = ["Sarah", "James", "Priya", "Tom", "Aisha", "Daniel", "Chloe", "Marek", "Fatima", "Owen", "Grace", "Liam", "Zara", "Ben", "Hannah"]
LAST = ["Jones", "Patel", "Smith", "Okafor", "Wright", "Nowak", "Hughes", "Khan", "Evans", "Clarke", "Murphy", "Lewis"]
STREETS = ["Mill Road", "Station Road", "Church Lane", "Victoria Street", "Park Avenue", "High Street", "Orchard Close", "Kings Road"]
STAFF = ["Megan", "Rob", "Asha", "Callum"]
URGENT = ["There's a strong smell of gas in the hallway", "Water is coming through the kitchen ceiling",
          "The boiler has failed and we have no heating or hot water", "The front door lock is broken and won't close"]
NON_URGENT = ["The kitchen tap has been dripping for a week", "The bathroom extractor fan has stopped working",
              "There's some mould starting on the bedroom wall", "One of the radiators isn't getting warm"]


def last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def bst_window_utc(year: int) -> tuple[datetime, datetime]:
    """BST runs from 01:00 UTC on the last Sunday of March to 01:00 UTC on the last Sunday of October."""
    return datetime.combine(last_sunday(year, 3), time(1)), datetime.combine(last_sunday(year, 10), time(1))


def is_bst(utc: datetime) -> bool:
    s, e = bst_window_utc(utc.year)
    return s <= utc < e


def local_to_utc(local: datetime) -> datetime:
    guess = local - timedelta(hours=1)
    return guess if is_bst(guess) else local


def utc_to_local(utc: datetime) -> datetime:
    return utc + timedelta(hours=1) if is_bst(utc) else utc


def pick(rng, weighted):
    r, acc = rng.random(), 0.0
    for v, w in weighted:
        acc += w
        if r < acc:
            return v
    return weighted[-1][0]


def fmt(ts: datetime | None) -> str:
    return "" if ts is None else ts.strftime("%Y-%m-%d %H:%M:%S")


class Person:
    def __init__(self, rng: random.Random, area: str):
        self.name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        n = rng.randint(100, 999)
        self.phone = rng.choice([f"07700 900{n}", f"+44 7700 900{n}", f"07700900{n}"])
        self.email = f"{self.name.split()[0].lower()}.{self.name.split()[1].lower()}{rng.randint(1, 99)}@example.com"
        self.street = f"{rng.randint(2, 120)} {rng.choice(STREETS)}"
        self.postcode = f"{area}{rng.randint(1, 15)} {rng.randint(1, 9)}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}"


def build_conversation(rng, conv, person, branch_name, local_start=None):
    """Return (turns, outcomes, truth). Turns are (sender, offset_seconds, body)."""
    ch, enq, variant = conv["channel"], conv["enquiry_type"], conv["greeting_variant"]
    slow = ch in ("email", "portal")
    def cust_gap():
        return rng.uniform(600, 6 * 3600) if slow else (rng.uniform(5, 25) if ch == "call" else rng.uniform(30, 600))
    def bot_gap():
        return rng.lognormvariate(*LATENCY[ch])

    greet = (f"Thanks for getting in touch with {branch_name}. How can I help?" if variant == "A"
             else f"Hi, thanks for contacting {branch_name}. I can book viewings and answer questions any time, day or night.")
    turns, outcomes, t = [], [], 0.0
    truth = {"details_captured": None, "next_step_offered": None, "safe_escalation": None, "urgent": 0}

    if enq == "lettings":
        first = f"Hi, is the {rng.randint(1, 4)} bed flat on {rng.choice(STREETS)} still available? I'm {person.name}, you can reach me on {person.phone} or {person.email}."
    elif enq == "sales":
        first = f"Hello, I'd like to view the house on {person.street}, {person.postcode}. {person.name}, {person.phone}."
    elif enq == "valuation":
        first = f"Could someone value my property at {person.street}, {person.postcode}? Thinking of selling in the spring. {person.email}"
    elif enq == "maintenance":
        truth["urgent"] = int(rng.random() < 0.3)
        issue = rng.choice(URGENT if truth["urgent"] else NON_URGENT)
        first = f"{issue} at {person.street}. This is {person.name}, {person.phone}."
    else:
        first = rng.choice(["What are your office opening hours over Christmas?", "Do you accept tenants with pets?",
                            "Can I get a copy of my tenancy agreement?"])
    turns.append(("customer", t, first))
    fast_handoff = False  # urgent repairs go to an on-call line that answers at any hour

    # A small share of conversations never get a reply (stuck in a queue)
    if rng.random() < 0.012:
        return turns, outcomes, truth

    t += bot_gap()
    handed = False
    if enq in ("lettings", "sales"):
        if enq == "lettings":
            r = rng.random()
            if r < 0.70:
                ask, truth["details_captured"] = "When are you looking to move in, and what's your monthly budget?", 1
            elif r < 0.88:  # captured, but phrased in a way a keyword judge can miss
                ask, truth["details_captured"] = "What date would you like the tenancy to start from, and what's your budget?", 1
            else:
                ask, truth["details_captured"] = "What's your monthly budget?", 0
            reply = f"Ideally from {rng.choice(['next month', 'January', 'mid December'])}, budget around £{rng.choice([950, 1100, 1250, 1400, 1650])} pcm."
        else:
            if rng.random() < 0.85:
                ask, truth["details_captured"] = "Are you a cash buyer, or do you have a mortgage in principle?", 1
            else:
                ask, truth["details_captured"] = "Is there anything else you'd like to know about the property?", 0
            reply = rng.choice(["Mortgage agreed in principle.", "Cash buyer, flat already sold.", "Still speaking to the bank."])
        turns.append(("felicity", t, f"{greet} {ask}"))
        t += cust_gap()
        turns.append(("customer", t, reply))
        t += bot_gap()
        p_view = 0.27 if variant == "A" else 0.305
        offered = rng.random() < 0.90
        truth["next_step_offered"] = int(offered)
        outcomes.append(("lead_qualified", t))
        if offered and rng.random() < p_view / 0.90:
            turns.append(("felicity", t, f"I can book you a viewing on {rng.choice(['Tuesday', 'Thursday', 'Saturday'])} at {rng.choice(['10:30', '12:00', '16:15'])}. Shall I confirm?"))
            t += cust_gap()
            turns.append(("customer", t, "Yes please."))
            t += bot_gap()
            turns.append(("felicity", t, f"Booked. You'll get a confirmation by {ch if ch != 'call' else 'text'}."))
            outcomes.append(("viewing_booked", t))
        elif offered:
            turns.append(("felicity", t, "I can book you a viewing this week if you'd like."))
            t += cust_gap()
            turns.append(("customer", t, "I'll check my diary and come back to you."))
        else:
            turns.append(("felicity", t, "Thanks, I've passed your details to the team."))
    elif enq == "valuation":
        turns.append(("felicity", t, f"{greet} Is the property currently occupied, and roughly when would you want to sell?"))
        t += cust_gap()
        turns.append(("customer", t, "Owner occupied, aiming for March."))
        t += bot_gap()
        outcomes.append(("lead_qualified", t))
        if rng.random() < 0.40:
            turns.append(("felicity", t, "I've booked a valuation visit for Wednesday at 11:00."))
            outcomes.append(("valuation_booked", t))
        else:
            turns.append(("felicity", t, "A valuer will call you to arrange a time."))
    elif enq == "maintenance":
        turns.append(("felicity", t, f"{greet} Sorry to hear that. Is anyone at risk right now?"))
        t += cust_gap()
        turns.append(("customer", t, "No one is hurt but it needs looking at."))
        t += bot_gap()
        if truth["urgent"]:
            escalate = rng.random() < 0.80
            truth["safe_escalation"] = int(escalate)
            if escalate:
                turns.append(("felicity", t, "This sounds urgent. I'm passing you to the emergency contractor line now."))
                handed = fast_handoff = True
            else:
                turns.append(("felicity", t, "I've logged this and the team will be in touch next working day."))
        else:
            turns.append(("felicity", t, "I've logged a repair job and the contractor will contact you to arrange a visit."))
        outcomes.append(("maintenance_triaged", t))
    else:
        turns.append(("felicity", t, f"{greet} The office is open Monday to Saturday; I can help with most questions now."))

    if not handed and rng.random() < 0.07:
        t += bot_gap()
        turns.append(("felicity", t, "Let me pass you to a member of the team."))
        handed = True
    if handed:
        outcomes.append(("handed_to_human", t))
        # Inside rough office hours a person picks up within minutes; outside, it waits for the morning.
        hand_local = (local_start or datetime(2026, 1, 5, 12)) + timedelta(seconds=t)
        office = hand_local.isoweekday() <= 6 and 9 <= hand_local.hour < 17
        t += rng.uniform(120, 1800) if (office or fast_handoff) else rng.uniform(5 * 3600, 14 * 3600)
        turns.append(("human_agent", t, f"Hi, this is {rng.choice(STAFF)} from the {branch_name} team. I'm picking this up now."))
    return turns, outcomes, truth


def generate(out_dir=config.RAW_DIR, truth_dir=config.TRUTH_DIR, seed=config.SEED) -> dict:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    agencies, branches, hours = [], [], []
    for ag_id, ag_name, crm, brs in AGENCIES:
        agencies.append([ag_id, ag_name, crm])
        for br_id, br_name, area, profile in brs:
            branches.append([br_id, ag_id, f"{ag_name} {br_name}", area])
            for dow, (o, c) in HOURS_PROFILES[profile].items():
                hours.append([br_id, dow, o + ":00", c + ":00"])

    conversations, messages, outcomes, leads, events, truth_rows = [], [], [], [], [], []
    conv_n = msg_n = out_n = lead_n = ev_n = 0
    crm_of = {a[0]: a[2] for a in agencies}
    lead_prefix = {"alto": "ALT", "mri": "MRI", "street": "STR", "loop": "LP"}

    days = (config.WINDOW_END_LOCAL - config.WINDOW_START_LOCAL).days
    for br_id, ag_id, br_name, area in branches:
        base = rng.uniform(7, 13)
        crm = crm_of[ag_id]
        for d in range(days):
            day = config.WINDOW_START_LOCAL + timedelta(days=d)
            wd = day.isoweekday()
            mean = base * (1.0 if wd <= 5 else 0.8 if wd == 6 else 0.6)
            n = max(0, int(round(rng.gauss(mean, math.sqrt(mean)))))
            weights = WEEKDAY_HOURS if wd <= 5 else WEEKEND_HOURS
            for _ in range(n):
                hour = rng.choices(range(24), weights=weights)[0]
                local = day + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
                start = local_to_utc(local)
                conv_n += 1
                cid = f"CV{conv_n:06d}"
                ch = pick(rng, CHANNELS)
                enq = pick(rng, ENQUIRIES)
                src = ("sms_gateway_v1" if rng.random() < 0.6 else "sms_gateway_v2") if ch == "sms" else \
                      "portal_ingest" if ch == "portal" else "felicity_core"
                conv = {"channel": ch, "enquiry_type": enq, "greeting_variant": "A" if rng.random() < 0.5 else "B"}
                person = Person(rng, area)
                turns, outs, truth = build_conversation(rng, conv, person, br_name, local)

                # Defect 2: legacy SMS gateway stores UK local time but labels it UTC.
                started_raw = start + timedelta(hours=1) if (src == "sms_gateway_v1" and is_bst(start)) else start
                conversations.append([cid, br_id, ch, enq, conv["greeting_variant"], src, fmt(started_raw),
                                      fmt(start + timedelta(seconds=rng.randint(30, 300)))])
                # Streamed: each message lands a few minutes after it is sent. Anything after
                # the as-of time has not arrived yet (conversations still in progress).
                for i, (sender, off, body) in enumerate(turns):
                    sent = start + timedelta(seconds=off)
                    ingested = sent + timedelta(seconds=rng.randint(30, 300))
                    if ingested >= config.AS_OF_UTC:
                        continue
                    msg_n += 1
                    messages.append([f"MS{msg_n:07d}", cid, i + 1, sender, fmt(sent), body, fmt(ingested)])
                for otype, off in outs:
                    if start + timedelta(seconds=off) >= config.AS_OF_UTC:
                        continue
                    out_n += 1
                    outcomes.append([f"OC{out_n:07d}", cid, otype, fmt(start + timedelta(seconds=off))])
                truth_rows.append([cid, enq, truth["urgent"], truth["details_captured"], truth["next_step_offered"], truth["safe_escalation"]])

                # CRM: qualified leads are pushed to the agency CRM. About 3.5% never arrive.
                types = {o[0] for o in outs}
                if "lead_qualified" in types and rng.random() > 0.035:
                    q_at = start + timedelta(seconds=dict(outs)["lead_qualified"])
                    created = q_at + timedelta(minutes=rng.randint(1, 10))
                    ingested = created + timedelta(minutes=rng.randint(30, 90))
                    if crm == "street" and ingested >= config.STREET_FEED_STOPPED_UTC:
                        continue  # Defect 6: feed stalled
                    if ingested >= config.AS_OF_UTC:
                        continue
                    lead_n += 1
                    lid = f"{lead_prefix[crm]}-{lead_n:06d}"
                    note = rng.choice(["", "", "", f"Called back on {person.phone}, prefers evenings",
                                       f"Sent particulars to {person.email}", "Asked about parking"])
                    status = "viewing_arranged" if "viewing_booked" in types or "valuation_booked" in types else "new"
                    row = [lid, crm, ag_id, cid, person.email, person.phone, fmt(created), status, note, fmt(ingested)]
                    leads.append(row)
                    # Defect 1: the CRM webhook sometimes fires twice and creates a second lead.
                    if rng.random() < 0.04:
                        lead_n += 1
                        dup = list(row)
                        dup[0] = f"{lead_prefix[crm]}-{lead_n:06d}"
                        dup[6] = fmt(created + timedelta(minutes=rng.randint(2, 30)))
                        leads.append(dup)
                    # Later conversions recorded in the CRM
                    if "viewing_booked" in types and rng.random() < 0.75:
                        when = created + timedelta(days=rng.uniform(1, 10))
                        chain = [("viewing_attended", when)]
                        if rng.random() < (0.35 if enq == "lettings" else 0.20):
                            chain.append(("let_agreed" if enq == "lettings" else "offer_accepted", when + timedelta(days=rng.uniform(1, 14))))
                    elif "valuation_booked" in types and rng.random() < 0.40:
                        chain = [("instruction_won", created + timedelta(days=rng.uniform(3, 20)))]
                    else:
                        chain = []
                    for etype, eat in chain:
                        eing = eat + timedelta(minutes=rng.randint(30, 90))
                        if eing >= config.AS_OF_UTC or (crm == "street" and eing >= config.STREET_FEED_STOPPED_UTC):
                            continue
                        ev_n += 1
                        events.append([f"EV{ev_n:07d}", lid, crm, etype, fmt(eat), fmt(eing)])

    # Leads that did not come through Felicity (walk-ins, direct portal) have no conversation id.
    for _ in range(int(len(leads) * 0.15)):
        ag_id, _, crm, _ = rng.choice(AGENCIES)
        created = local_to_utc(config.WINDOW_START_LOCAL + timedelta(days=rng.uniform(0, days)))
        ingested = created + timedelta(minutes=rng.randint(30, 90))
        if ingested >= config.AS_OF_UTC or (crm == "street" and ingested >= config.STREET_FEED_STOPPED_UTC):
            continue
        lead_n += 1
        p = Person(rng, "XX")
        leads.append([f"{lead_prefix[crm]}-{lead_n:06d}", crm, ag_id, "", p.email, p.phone, fmt(created), "new", "Walk-in", fmt(ingested)])

    # Defect 3: some conversation rows never arrive, but their messages and outcomes do.
    dropped = set(rng.sample([c[0] for c in conversations], k=int(len(conversations) * 0.005)))
    conversations = [c for c in conversations if c[0] not in dropped]
    leads = [l for l in leads if l[3] not in dropped]
    # Defect 5: ingest retries duplicate some message rows.
    messages += [list(m) for m in rng.sample(messages, k=int(len(messages) * 0.003))]

    def write(name, header, rows, folder=out_dir):
        with open(folder / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(["" if v is None else v for v in r] for r in rows)

    write("agencies", ["agency_id", "agency_name", "crm_system"], agencies)
    write("branches", ["branch_id", "agency_id", "branch_name", "postcode_area"], branches)
    write("branch_hours", ["branch_id", "day_of_week", "opens_local", "closes_local"], hours)
    write("conversations", ["conversation_id", "branch_id", "channel", "enquiry_type", "greeting_variant", "source_system", "started_at", "ingested_at"], conversations)
    write("messages", ["message_id", "conversation_id", "turn_index", "sender", "sent_at", "body", "ingested_at"], messages)
    write("outcomes", ["outcome_id", "conversation_id", "outcome_type", "outcome_at"], outcomes)
    write("crm_leads", ["crm_lead_id", "crm_system", "agency_id", "conversation_id", "contact_email", "contact_phone", "created_at", "status", "notes", "ingested_at"], leads)
    write("crm_events", ["crm_event_id", "crm_lead_id", "crm_system", "event_type", "event_at", "ingested_at"], events)

    clock = []
    for y in (2025, 2026, 2027):
        s, e = bst_window_utc(y)
        clock.append([y, fmt(s), fmt(e)])
    write("uk_clock_changes", ["year", "bst_starts_utc", "bst_ends_utc"], clock)
    write("bank_holidays", ["holiday_date", "region"], [[d.isoformat(), "england-and-wales"] for d in BANK_HOLIDAYS])
    write("reporting_window", ["window_start_local", "window_end_local", "as_of_utc"],
          [[fmt(config.WINDOW_START_LOCAL), fmt(config.WINDOW_END_LOCAL), fmt(config.AS_OF_UTC)]])
    write("quality_truth", ["conversation_id", "enquiry_type", "urgent", "details_captured", "next_step_offered", "safe_escalation"],
          truth_rows, folder=truth_dir)

    return {"conversations": len(conversations), "messages": len(messages), "outcomes": len(outcomes),
            "crm_leads": len(leads), "crm_events": len(events), "dropped_conversations": len(dropped)}


if __name__ == "__main__":
    print(generate())
