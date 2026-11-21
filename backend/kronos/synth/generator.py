"""KRONOS synthetic investigation-data generator.

Produces five interlinked CSVs (FIR, CDR, LOCATION, FINANCIAL_TRANSACTIONS,
SOCIAL_MEDIA_CHATS) plus ground_truth.json (used ONLY for evaluation).

Design: the generator simulates *humans* that move through a set of real places on a
daily routine. Every record (call, ping, message, payment) is produced from the human's
position at that moment, so all sources agree with each other. Case scenarios are then
scripted on top (meetings, incidents, money flows), together with deliberate
counter-examples (innocent shared places, legitimate large payments, namesakes, cell
handovers, plausible flights) so analytics can be tested for false positives.
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import world as W


@dataclass
class SynthConfig:
    seed: int = 42
    n_cases: int = 40
    n_people: int = 420
    n_orgs: int = len(W.ORGS)
    start_date: str = "2025-01-01"
    days: int = 181
    n_agencies: int = 4
    n_cdr: int = 7000
    n_social: int = 5000
    n_location: int = 12000
    n_transactions: int = 5000
    n_fir_extra_statements: int = 60      # witness/supplementary statements beyond one FIR per case
    n_alias_pairs: int = 8
    n_namesakes: int = 6
    n_repeat_offenders: int = 14
    n_shared_devices: int = 5
    n_impossible_travel: int = 10
    n_burner_pairs: int = 4               # same human, later case, new name + new phone/SIM/handset/account
    n_history_other: int = 20             # prior records for people not among the repeat offenders
    n_history_noise: int = 25             # prior records of people who are NOT in the current data (incl. same-name traps)
    malformed_rate: float = 0.004
    out_dir: str = "data/generated"


# ----------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------
PLACE = {p[0]: dict(id=p[0], name=p[1], city=p[2], type=p[3], lat=p[4], lon=p[5]) for p in W.PLACES}


def haversine_km(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def places_in(city, types=None):
    return [p for p in PLACE.values() if p["city"] == city and (types is None or p["type"] in types)]


@dataclass
class Human:
    hid: str
    name: str
    gender: str
    city: str
    home: str
    work: str
    leisure: list
    phones: list
    devices: list
    sims: list
    accounts: list          # list of (account_no, bank_name)
    employer: str | None
    family: list = field(default_factory=list)
    colleagues: list = field(default_factory=list)
    friends: list = field(default_factory=list)
    overrides: list = field(default_factory=list)   # (start, end, place_id, tag)
    busy: list = field(default_factory=list)        # (start, end) windows where routine sampling is blocked
    father: str = ""
    birth_year: int = 1985
    burner: bool = False


@dataclass
class PersonRecord:
    pid: str
    hid: str
    name: str
    phone_idx: int = 0
    device_idx: int = 0
    account_idx: int = 0
    windows: list = field(default_factory=list)     # (case_id, start, end)
    father: str | None = None                       # father's name as *stated* for this record (may be false)
    address: str | None = None                      # residence as *stated* for this record


class Generator:
    def __init__(self, cfg: SynthConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.t0 = datetime.fromisoformat(cfg.start_date)
        self.t_end = self.t0 + timedelta(days=cfg.days)
        self.humans: dict[str, Human] = {}
        self.persons: dict[str, PersonRecord] = {}
        self.h2p: dict[str, list[str]] = defaultdict(list)
        self.orgs = {o[0]: dict(id=o[0], name=o[1], kind=o[2], city=o[3]) for o in W.ORGS[: cfg.n_orgs]}
        self.rows = {k: [] for k in ("FIR", "CDR", "LOCATION", "FIN", "SOCIAL", "HISTORY")}
        self.cases: dict[str, dict] = {}
        self.gt = defaultdict(list)          # ground truth collections
        self.used_names = set()
        self.agency_map = self._agency_map()

    # ------------------------------------------------------------------ identities
    def _agency_map(self):
        ids = list(W.AGENCIES)[: max(1, self.cfg.n_agencies)]
        m = {}
        for city, (_, ag, _) in W.CITIES.items():
            if ag is None:
                continue
            m[city] = ag if ag in ids else ids[hash(ag) % len(ids)]
        return m

    def _digits(self, n):
        return "".join(self.rng.choice("0123456789") for _ in range(n))

    def _phone(self):
        return f"+91-{self.rng.choice('6789')}{self._digits(9)}"

    def _device(self):
        return f"IMEI-35{self._digits(13)}"

    def _sim(self):
        return f"SIM-8991{self._digits(12)}"

    def _account(self):
        code, bank = self.rng.choice(W.BANKS)
        return (f"{code}-{self._digits(11)}", bank)

    def _unique_name(self, gender):
        for _ in range(500):
            first = self.rng.choice(W.MALE_FIRST if gender == "M" else W.FEMALE_FIRST)
            sur = self.rng.choice(W.SURNAMES)
            if gender == "F" and sur == "Singh" and self.rng.random() < 0.6:
                sur = "Kaur"
            if gender == "M" and sur == "Kaur":
                sur = "Singh"
            n = f"{first} {sur}"
            if n not in self.used_names and n not in W.NAMESAKES:
                self.used_names.add(n)
                return n
        return f"{first} {sur} {self._digits(2)}"

    def _new_human(self, name=None, gender=None, city=None) -> Human:
        hid = f"H{len(self.humans) + 1:04d}"
        gender = gender or ("M" if self.rng.random() < 0.72 else "F")
        name = name or self._unique_name(gender)
        city = city or self.rng.choice(W.CASE_CITIES)
        homes = places_in(city, {"RESIDENTIAL"}) or places_in(city)
        works = places_in(city, {"OFFICE", "MARKET", "COMMERCIAL"}) or places_in(city)
        leis = places_in(city, {"MARKET", "COMMERCIAL", "PUBLIC", "TRANSIT"}) or places_in(city)
        employers = [o for o in self.orgs.values() if o["kind"] == "EMPLOYER" and o["city"] == city]
        h = Human(
            hid=hid, name=name, gender=gender, city=city,
            home=self.rng.choice(homes)["id"], work=self.rng.choice(works)["id"],
            leisure=[p["id"] for p in self.rng.sample(leis, min(2, len(leis)))],
            phones=[self._phone() for _ in range(1 if self.rng.random() < 0.75 else 2)],
            devices=[self._device()], sims=[], accounts=[self._account() for _ in range(1 if self.rng.random() < 0.7 else 2)],
            employer=(self.rng.choice(employers)["id"] if employers and self.rng.random() < 0.7 else None),
        )
        h.sims = [self._sim() for _ in h.phones]
        sur = name.split()[-1] if name.split()[-1] not in ("Kaur",) else "Singh"
        h.father = f"{self.rng.choice(W.FATHER_FIRST)} {sur}"
        h.birth_year = self.rng.randint(1964, 2003)
        self.humans[hid] = h
        return h

    def _new_person(self, h: Human, name=None, phone_idx=0) -> PersonRecord:
        pid = f"P{len(self.persons) + 1:05d}"
        p = PersonRecord(pid=pid, hid=h.hid, name=name or h.name, phone_idx=phone_idx)
        self.persons[pid] = p
        self.h2p[h.hid].append(pid)
        return p

    def build_population(self):
        cfg = self.cfg
        # namesakes: same name, different humans, different cities and phones
        for name in W.NAMESAKES[: cfg.n_namesakes]:
            cities = self.rng.sample(["Chandigarh", "Delhi", "Ludhiana", "Ambala", "Gurugram", "Mohali"], 2)
            g = "F" if name.split()[0] in W.FEMALE_FIRST else "M"
            pids = []
            for c in cities:
                h = self._new_human(name=name, gender=g, city=c)
                pids.append(self._new_person(h).pid)
            self.gt["namesakes"].append({"name": name, "person_ids": pids, "same_human": False})
        # alias humans: one human, two person records with different names
        for formal, alias in W.ALIAS_PAIRS[: cfg.n_alias_pairs]:
            h = self._new_human(name=formal, gender="M")
            if self.rng.random() < 0.5:   # alias record uses the human's 2nd phone (harder case)
                h.phones.append(self._phone()); h.sims.append(self._sim())
            a = self._new_person(h)
            b = self._new_person(h, name=alias, phone_idx=len(h.phones) - 1)
            self.gt["alias_pairs"].append({"human": h.hid, "person_ids": [a.pid, b.pid], "names": [formal, alias],
                                           "shares_phone": b.phone_idx == 0})
        # burner identities: the same human later uses a different name, phone, SIM, handset and bank account,
        # gives a false father's name and often a false address. No identifier is shared between the two
        # records — only behaviour (routine, places, social circle, timing) links them.
        for _ in range(cfg.n_burner_pairs):
            h = self._new_human(gender="M")
            h.burner = True
            a = self._new_person(h)
            h.phones.append(self._phone()); h.sims.append(self._sim()); h.devices.append(self._device())
            h.accounts.append(self._account())
            b = self._new_person(h, name=self._unique_name("M"), phone_idx=len(h.phones) - 1)
            b.device_idx, b.account_idx = len(h.devices) - 1, len(h.accounts) - 1
            b.father = f"{self.rng.choice(W.FATHER_FIRST)} {b.name.split()[-1]}"
            if self.rng.random() < 0.5:
                b.address = self.rng.choice(places_in(h.city, {"RESIDENTIAL"}) or places_in(h.city))["name"]
            self.gt["burner_pairs"].append({"human": h.hid, "person_ids": [a.pid, b.pid], "names": [a.name, b.name],
                                            "shared_identifiers": []})
        while len(self.humans) < cfg.n_people:
            self._new_person(self._new_human())
        # social ties
        hs = list(self.humans.values())
        by_city = defaultdict(list)
        for h in hs:
            by_city[h.city].append(h)
        by_emp = defaultdict(list)
        for h in hs:
            if h.employer:
                by_emp[h.employer].append(h)
        for h in hs:
            pool = [x for x in by_city[h.city] if x.hid != h.hid]
            h.family = [x.hid for x in self.rng.sample(pool, min(len(pool), self.rng.randint(1, 3)))]
            col = [x for x in by_emp.get(h.employer, []) if x.hid != h.hid]
            h.colleagues = [x.hid for x in self.rng.sample(col, min(len(col), self.rng.randint(1, 4)))] if col else []
            h.friends = [x.hid for x in self.rng.sample(pool, min(len(pool), self.rng.randint(1, 3)))]

    # ------------------------------------------------------------------ positions
    def _block(self, h: Human, start, end, place_id):
        """Reserve a scripted window, with travel buffer so routine pings never create
        unintended impossible travel around it."""
        home = PLACE[h.home]
        dist = haversine_km(home["lat"], home["lon"], PLACE[place_id]["lat"], PLACE[place_id]["lon"])
        buf = timedelta(hours=max(1.0, dist / 60.0))
        h.overrides.append((start, end, place_id))
        h.busy.append((start - buf, end + buf))

    def position(self, h: Human, t: datetime):
        for s, e, pl in h.overrides:
            if s <= t <= e:
                return pl
        for s, e in h.busy:
            if s <= t <= e:
                return None            # travelling – no routine record
        hr = t.hour + t.minute / 60
        weekday = t.weekday() < 6
        works = weekday and h.employer is not None
        # commute windows: the person is in transit, so no fixed position is recorded
        if works and (8.75 <= hr < 9.5 or 18.0 <= hr < 18.6):
            return None
        out_tonight = (int(h.hid[1:]) * 7 + t.toordinal()) % 2 == 0       # deterministic per person-day
        if out_tonight and (17.5 <= hr < 18.0 or 21.2 <= hr < 21.8):
            return None
        if hr < 8 or hr >= 22:
            return h.home
        if works and 9.5 <= hr < 18:
            return h.work
        if 18 <= hr < 21.5 and out_tonight:
            return h.leisure[t.toordinal() % len(h.leisure)]
        return h.home if (hr < 9.5 or hr >= 18) else (h.work if h.employer else h.leisure[0])

    def _jit(self, place_id, meters):
        p = PLACE[place_id]
        d = meters / 111_320
        return (round(p["lat"] + self.rng.uniform(-d, d), 6),
                round(p["lon"] + self.rng.uniform(-d, d) / max(0.2, math.cos(math.radians(p["lat"]))), 6))

    def _rand_time(self, start: datetime, end: datetime, day_hours=(7, 23)):
        start, end = max(start, self.t0), min(end, self.t_end)
        if end <= start:
            return None
        for _ in range(8):
            t = start + timedelta(seconds=self.rng.uniform(0, (end - start).total_seconds()))
            h = self.rng.uniform(*day_hours) if self.rng.random() < 0.9 else self.rng.uniform(0, 24)
            t = t.replace(hour=int(h) % 24, minute=int((h % 1) * 60), second=self.rng.randint(0, 59))
            if start <= t <= end:
                return t
        return None

    # ------------------------------------------------------------------ record emitters
    def _rel(self, weights):
        return self.rng.choices(["HIGH", "MEDIUM", "LOW"], weights=weights)[0]

    def ping(self, pid, t, case_id, source=None, place=None, tag=None, block=True):
        p = self.persons[pid]; h = self.humans[p.hid]
        if place and block and not any(s <= t <= e for s, e, _ in h.overrides):
            self._block(h, t - timedelta(minutes=20), t + timedelta(minutes=20), place)
        place = place or self.position(h, t)
        if place is None:
            return None
        source = source or self.rng.choices(["GPS", "CELL_TOWER", "CHECKIN"], [0.5, 0.42, 0.08])[0]
        acc = {"GPS": self.rng.uniform(8, 60), "CELL_TOWER": self.rng.uniform(400, 2500), "CHECKIN": 30.0}[source]
        lat, lon = self._jit(place, acc * 0.6)
        row = dict(
            case_id=case_id, person_id=pid, phone_number=h.phones[min(p.phone_idx, len(h.phones) - 1)],
            device_id=h.devices[min(p.device_idx, len(h.devices) - 1)], timestamp=t, latitude=lat, longitude=lon,
            accuracy_m=round(acc, 1), location_name=PLACE[place]["name"], place_id=place, location_type=PLACE[place]["type"],
            source_type=source, source_reliability={"GPS": "HIGH", "CELL_TOWER": "MEDIUM", "CHECKIN": "LOW"}[source],
            _tag=tag)
        self.rows["LOCATION"].append(row)
        return row

    def _active_record(self, pid, t):
        """For humans with several person records, contacts reach whichever identity is in use at time t."""
        recs = self.h2p[self.persons[pid].hid]
        if len(recs) == 1:
            return pid
        for r in recs:
            if any(ws <= t <= we for _, ws, we in self.persons[r].windows):
                return r
        dist = lambda r: min([abs((t - ws).total_seconds()) for _, ws, _ in self.persons[r].windows] or [1e18])
        return min(recs, key=dist)

    def call(self, a, b, t, case_id, dur=None, tag=None, call_type="VOICE"):
        b = self._active_record(b, t)
        pa, pb = self.persons[a], self.persons[b]
        ha, hb = self.humans[pa.hid], self.humans[pb.hid]
        place = self.position(ha, t)
        if place is None:
            return None
        lat, lon = self._jit(place, 1500)
        dur = dur if dur is not None else (0 if call_type == "SMS" else int(min(3600, self.rng.lognormvariate(4.2, 0.9))))
        row = dict(case_id=case_id, caller_person_id=a, caller_name=pa.name,
                   caller_number=ha.phones[min(pa.phone_idx, len(ha.phones) - 1)],
                   receiver_person_id=b, receiver_name=pb.name,
                   receiver_number=hb.phones[min(pb.phone_idx, len(hb.phones) - 1)],
                   timestamp=t, duration_sec=dur, call_type=call_type,
                   imei=ha.devices[min(pa.device_idx, len(ha.devices) - 1)],
                   imsi=ha.sims[min(pa.phone_idx, len(ha.sims) - 1)],
                   cell_tower_id=f"TWR-{place[4:7]}-{abs(hash((place, round(lat, 2)))) % 900 + 100}",
                   tower_lat=lat, tower_lon=lon, tower_location=PLACE[place]["name"],
                   call_status="ANSWERED" if dur > 0 or call_type == "SMS" else "MISSED",
                   source_reliability=self._rel([0.85, 0.13, 0.02]), _tag=tag)
        self.rows["CDR"].append(row)
        return row

    def msg(self, a, b, t, case_id, text, tag=None, platform=None):
        b = self._active_record(b, t)
        pa, pb = self.persons[a], self.persons[b]
        ha, hb = self.humans[pa.hid], self.humans[pb.hid]
        place = self.position(ha, t)
        if place is None:
            return None
        lat, lon = self._jit(place, 80)
        text = text.replace("{place}", PLACE[place]["name"].split(",")[0])
        platform = platform or self.rng.choices(["WhatsApp", "Telegram", "SMS", "Instagram"], [0.6, 0.18, 0.15, 0.07])[0]
        row = dict(case_id=case_id, platform=platform, timestamp=t, sender_person_id=a, sender_name=pa.name,
                   sender_handle=f"@{pa.name.split()[0].lower()}{pa.pid[-3:]}",
                   sender_phone=ha.phones[min(pa.phone_idx, len(ha.phones) - 1)],
                   receiver_person_id=b, receiver_name=pb.name,
                   receiver_handle=f"@{pb.name.split()[0].lower()}{pb.pid[-3:]}",
                   receiver_phone=hb.phones[min(pb.phone_idx, len(hb.phones) - 1)],
                   message_text=text, device_id=ha.devices[min(pa.device_idx, len(ha.devices) - 1)],
                   latitude=lat, longitude=lon,
                   source_reliability=self._rel([0.35, 0.5, 0.15]), _tag=tag)
        self.rows["SOCIAL"].append(row)
        return row

    def _acct(self, pid, idx=None):
        p = self.persons[pid]; h = self.humans[p.hid]
        i = p.account_idx if idx is None else idx
        return h.accounts[min(i, len(h.accounts) - 1)]

    def txn(self, t, case_id, amount, channel, purpose, sender=None, receiver=None, s_org=None, r_org=None,
            tag=None, s_acct=None, r_acct=None, place=None):
        def side(pid, org, acct):
            if org:
                o = self.orgs[org]
                if "account" not in o:
                    o["account"] = self._account()
                return None, o["name"], (acct or o["account"]), org
            p = self.persons[pid]
            return pid, p.name, (acct or self._acct(pid)), None
        s_pid, s_name, (s_no, s_bank), s_oid = side(sender, s_org, s_acct)
        if receiver and not r_org:
            receiver = self._active_record(receiver, t)
        r_pid, r_name, (r_no, r_bank), r_oid = side(receiver, r_org, r_acct)
        if place is None and s_pid:
            place = self.position(self.humans[self.persons[s_pid].hid], t)
        # many digital transactions carry no location; only record one when it is known
        lat, lon = self._jit(place, 200) if place else ("", "")
        row = dict(case_id=case_id, timestamp=t, sender_person_id=s_pid, sender_name=s_name, sender_account=s_no,
                   sender_bank=s_bank, sender_org_id=s_oid, receiver_person_id=r_pid, receiver_name=r_name,
                   receiver_account=r_no, receiver_bank=r_bank, receiver_org_id=r_oid, amount=round(amount, 2),
                   currency="INR", channel=channel, purpose=purpose, status="SUCCESS",
                   location_name=PLACE[place]["name"] if place else "", latitude=lat, longitude=lon,
                   source_reliability=self._rel([0.9, 0.09, 0.01]), _tag=tag)
        self.rows["FIN"].append(row)
        return row

    # ------------------------------------------------------------------ cases
    def _pick_subject(self, city=None, exclude=()):
        reserved = set(getattr(self, "repeat_pool", []))
        ok = lambda p: (p.pid not in exclude and not p.windows and p.hid not in reserved
                        and len(self.h2p[p.hid]) == 1)
        cands = [p for p in self.persons.values() if ok(p) and (city is None or self.humans[p.hid].city == city)]
        if not cands:
            cands = [p for p in self.persons.values() if ok(p)]
        return self.rng.choice(cands).pid

    def build_cases(self):
        cfg = self.cfg
        scen = list(W.SCENARIO_WEIGHTS)
        # Repeat offenders: humans who will be accused in several cases. Alias humans are included
        alias_humans = [g["human"] for g in self.gt["alias_pairs"]] + [g["human"] for g in self.gt["burner_pairs"]]
        self.first_use: dict[str, datetime] = {}
        self.repeat_pool = alias_humans + [p.hid for p in self.rng.sample(list(self.persons.values()), cfg.n_repeat_offenders)]
        self.repeat_pool = list(dict.fromkeys(self.repeat_pool))[: cfg.n_repeat_offenders + len(alias_humans)]
        self.human_use = defaultdict(int)
        span = cfg.days - 40
        for i in range(cfg.n_cases):
            cid = f"CASE{i + 1:03d}"
            s = self.rng.choices(scen, [W.SCENARIO_WEIGHTS[x] for x in scen])[0]
            city = self.rng.choice(W.CASE_CITIES)
            day = int(20 + (i * span / cfg.n_cases) + self.rng.uniform(0, span / cfg.n_cases))
            inc = (self.t0 + timedelta(days=day)).replace(hour=self.rng.randint(9, 20), minute=self.rng.randint(0, 59))
            inc = inc.replace(second=0, microsecond=0)
            district, _, stations = W.CITIES[city]
            case = dict(case_id=cid, scenario=s, city=city, district=district, agency_id=self.agency_map[city],
                        police_station=self.rng.choice(stations), incident_ts=inc,
                        registration_ts=inc + timedelta(hours=self.rng.choice([2, 5, 9, 20, 30, 52, 76, 110])
                                                        + self.rng.random()),
                        offence_category=W.SCENARIOS[s][0], sections=W.SCENARIOS[s][1],
                        title=self.rng.choice(W.SCENARIOS[s][2]) + f" — {city}",
                        lead_investigator=self.rng.choice(W.INVESTIGATORS), roles={}, truth={})
            self.cases[cid] = case
            getattr(self, f"_scenario_{s.lower()}")(case)
        # namesakes: both bearers of the same name appear (as witnesses) in different cases
        all_cases = list(self.cases.values())
        for ns in self.gt["namesakes"]:
            for pid in ns["person_ids"]:
                if self.persons[pid].windows:
                    continue
                c = self.rng.choice(all_cases)
                self._enroll(c, pid, "WITNESS", before=15, after=15)
                c.setdefault("late_witnesses", []).append(pid)
        for c in all_cases:
            self.gt["cases"].append({"case_id": c["case_id"], "scenario": c["scenario"], "roles": c["roles"], "truth": c["truth"]})

    def _accused_pids(self, case, k):
        """Choose accused; sometimes reuse a repeat offender (possibly via their alias record)."""
        out = []
        for _ in range(k):
            pid = None
            if self.rng.random() < 0.5:
                cands = [h for h in self.repeat_pool if self.human_use[h] < 3]
                self.rng.shuffle(cands)
                # alias humans whose second record is still unused go first (ensures cross-case aliases exist)
                cands.sort(key=lambda h: (len(self.h2p[h]) == 1, self.human_use[h]))
                for hid in cands:
                    recs = self.h2p[hid]
                    # a human's n-th case uses the n-th person record when available (alias in later cases)
                    rec = recs[min(self.human_use[hid], len(recs) - 1)]
                    h = self.humans[hid]
                    # a burner identity only appears once the earlier identity has gone quiet (≥70 days later)
                    if h.burner and self.human_use[hid] >= 1 and \
                            (case["incident_ts"] - self.first_use.get(hid, case["incident_ts"])).days < 70:
                        continue
                    if h.burner and self.human_use[hid] >= 2:
                        continue
                    if rec not in out and not any(w[0] == case["case_id"] for w in self.persons[rec].windows):
                        pid = rec
                        break
            if pid is None:
                pid = self._pick_subject(case["city"] if self.rng.random() < 0.7 else None, exclude=out)
            self.human_use[self.persons[pid].hid] += 1
            self.first_use.setdefault(self.persons[pid].hid, case["incident_ts"])
            out.append(pid)
        return out

    def _enroll(self, case, pid, role, before=30, after=30):
        case["roles"].setdefault(pid, [])
        if role not in case["roles"][pid]:
            case["roles"][pid].append(role)
        p = self.persons[pid]
        if not any(w[0] == case["case_id"] for w in p.windows):
            inc = case["incident_ts"]
            p.windows.append((case["case_id"], inc - timedelta(days=before), inc + timedelta(days=after)))

    def _meeting(self, case, pids, t, place, mins=45, tag="MEETING"):
        for pid in pids:
            h = self.humans[self.persons[pid].hid]
            self._block(h, t - timedelta(minutes=10), t + timedelta(minutes=mins), place)
            self.ping(pid, t + timedelta(minutes=self.rng.randint(0, mins // 2)), case["case_id"], "GPS", place, tag)
        self.gt["meetings"].append({"case_id": case["case_id"], "person_ids": pids, "ts": t, "place": place})

    def _burst(self, case, a, b, around, n=6, hours=3, tag="BURST"):
        for _ in range(n):
            t = around + timedelta(minutes=self.rng.uniform(-hours * 60, hours * 60))
            self.call(a, b, t, case["case_id"], tag=tag) if self.rng.random() < 0.7 else \
                self.call(b, a, t, case["case_id"], tag=tag)

    def _particulars(self, pid) -> str:
        p = self.persons[pid]; h = self.humans[p.hid]
        father = p.father or h.father
        addr = p.address or PLACE[h.home]["name"]
        return f"{p.name} S/o {father}, R/o {addr}"

    def _fir(self, case, narrative, complainant, accused, kind="FIR", reg=None, reliability="HIGH"):
        reg = reg or case["registration_ts"]
        if kind == "FIR" and accused:
            narrative += " Particulars of accused: " + "; ".join(f"{i + 1}) {self._particulars(a)}" for i, a in enumerate(accused)) + "."
        row = dict(case_id=case["case_id"], record_type=kind, police_station=case["police_station"],
                   district=case["district"], agency_id=case["agency_id"], registration_ts=reg,
                   incident_ts=case["incident_ts"], offence_category=case["offence_category"],
                   sections=case["sections"], complainant_person_id=complainant,
                   complainant_name=self.persons[complainant].name if complainant else "",
                   accused_person_ids=";".join(accused), incident_location=PLACE[case["place"]]["name"],
                   incident_lat=PLACE[case["place"]]["lat"], incident_lon=PLACE[case["place"]]["lon"],
                   narrative=narrative, source_reliability=reliability, _tag=kind)
        self.rows["FIR"].append(row)
        return row

    def _ph(self, pid):
        p = self.persons[pid]; h = self.humans[p.hid]
        return h.phones[min(p.phone_idx, len(h.phones) - 1)]

    def _n(self, pid, alias=True):
        """Name as it would appear in an FIR, occasionally with a known alias (Name @ Alias)."""
        p = self.persons[pid]
        recs = self.h2p[p.hid]
        if alias and len(recs) > 1 and not self.humans[p.hid].burner and self.rng.random() < 0.35:
            other = [self.persons[r].name for r in recs if r != pid][0]
            return f"{p.name} @ {other}"
        return p.name

    @staticmethod
    def _dt(t):
        return t.strftime("%d/%m/%Y at about %H:%M hrs")

    # ---- individual scenarios --------------------------------------------------------
    def _scenario_investment_fraud(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        case["place"] = self.rng.choice(places_in(case["city"], {"RESIDENTIAL"}) or places_in(case["city"]))["id"]
        accused = self._accused_pids(case, self.rng.randint(1, 2))
        mules = [self._pick_subject() for _ in range(self.rng.randint(2, 3))]
        victims = [self._pick_subject(case["city"], exclude=accused + mules) for _ in range(self.rng.randint(2, 3))]
        for a in accused: self._enroll(case, a, "ACCUSED")
        for m in mules: self._enroll(case, m, "ASSOCIATE")
        for v in victims: self._enroll(case, v, "VICTIM")
        case["roles"][victims[0]] = ["COMPLAINANT", "VICTIM"]
        case["truth"] = {"involved": accused + mules, "pattern": "victims->mules->accused rapid layering"}
        lead = accused[0]
        # lure messages and victim deposits (repeated small transfers)
        total = 0
        for v in victims:
            for k in range(self.rng.randint(3, 6)):
                t = inc - timedelta(days=self.rng.uniform(0, 12), hours=self.rng.uniform(0, 5))
                amt = self.rng.choice([9999, 24999, 49000, 15000, 30000, 45000])
                m = self.rng.choice(mules)
                self.msg(lead, v, t - timedelta(minutes=20), cid,
                         f"Your returns of 18% are credited. Add Rs {amt:,} more to unlock withdrawal. Transfer to {self._acct(m)[0]}.",
                         tag="LURE", platform="Telegram")
                r = self.txn(t, cid, amt, "UPI", "investment", sender=v, receiver=m, tag="VICTIM_TO_MULE")
                self.gt["fin_anomalies"].append({"ref": id(r), "type": "REPEATED_SMALL_TRANSFERS"})
                total += amt
        # mules forward quickly to accused (layering) then cash-out
        for m in mules:
            for k in range(self.rng.randint(2, 3)):
                t = inc + timedelta(hours=self.rng.uniform(1, 30))
                amt = round(total / len(mules) / 2 * self.rng.uniform(0.85, 1.0), 2)
                r1 = self.txn(t, cid, amt, "IMPS", "transfer", sender=m, receiver=lead, tag="LAYERING")
                r2 = self.txn(t + timedelta(minutes=self.rng.randint(8, 50)), cid, amt * 0.97, "IMPS", "transfer",
                              sender=lead, receiver=accused[-1], tag="LAYERING", s_acct=self._acct(lead, 1),
                              r_acct=self._acct(accused[-1], 0))
                self.gt["fin_anomalies"] += [{"ref": id(r1), "type": "RAPID_SEQUENCE"}, {"ref": id(r2), "type": "RAPID_SEQUENCE"}]
            self._burst(case, lead, m, inc + timedelta(hours=6), n=4)
        cash = self.txn(inc + timedelta(days=2), cid, total * 0.8, "CASH_WITHDRAWAL", "self", sender=accused[-1],
                        r_org=None, receiver=accused[-1], tag="CASHOUT")
        self.gt["fin_anomalies"].append({"ref": id(cash), "type": "LARGE_AMOUNT"})
        names = ", ".join(self._n(v) for v in victims[1:])
        narr = (f"The complainant {self._n(victims[0], False)} (mobile {self._ph(victims[0])}), resident of "
                f"{PLACE[self.humans[self.persons[victims[0]].hid].home]['name']}, stated that between "
                f"{(inc - timedelta(days=12)).strftime('%d/%m/%Y')} and {self._dt(inc)} he was contacted on Telegram by a person "
                f"who introduced himself as {self._n(lead)} (mobile {self._ph(lead)}), promising 18% weekly returns on stock trading. "
                f"The complainant transferred money to account {self._acct(mules[0])[0]} and other accounts. "
                f"Other victims {names} reported similar losses. The accused {self._n(lead)} "
                + (f"and co-accused {self._n(accused[1])} " if len(accused) > 1 else "")
                + f"stopped responding. Total loss reported is approximately Rs {total:,.0f}.")
        self._fir(case, narr, victims[0], accused)

    def _scenario_shell_layering(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        case["place"] = self.rng.choice(places_in(case["city"], {"COMMERCIAL", "OFFICE", "MARKET"}) or places_in(case["city"]))["id"]
        accused = self._accused_pids(case, self.rng.randint(2, 3))
        accountant = self._pick_subject(case["city"], exclude=accused)
        complainant = self._pick_subject(case["city"], exclude=accused + [accountant])
        witness = self._pick_subject(case["city"], exclude=accused + [accountant, complainant])
        for a in accused: self._enroll(case, a, "ACCUSED")
        self._enroll(case, accountant, "WITNESS"); self._enroll(case, complainant, "COMPLAINANT")
        self._enroll(case, witness, "WITNESS")
        shells = self.rng.sample([o for o in self.orgs if self.orgs[o]["kind"] == "SHELL"], 2)
        case["truth"] = {"involved": accused, "pattern": "company funds -> shell firms -> split to accused accounts",
                         "shells": shells, "innocent_witness": [accountant, witness]}
        meet = places_in(case["city"], {"COMMERCIAL", "PUBLIC"}) or places_in(case["city"])
        self._meeting(case, accused, inc - timedelta(days=3, hours=2), self.rng.choice(meet)["id"])
        self._burst(case, accused[0], accused[1], inc - timedelta(days=1), n=8)
        employer = self.humans[self.persons[complainant].hid].employer or "ORG-001"
        big = self.rng.choice([1850000, 2400000, 3200000, 4250000])
        r = self.txn(inc, cid, big, "RTGS", "invoice payment INV-" + self._digits(5), s_org=employer, r_org=shells[0],
                     tag="LARGE_TO_SHELL", place=case["place"])
        self.gt["fin_anomalies"].append({"ref": id(r), "type": "LARGE_AMOUNT"})
        r = self.txn(inc + timedelta(minutes=40), cid, big * 0.98, "RTGS", "advance", s_org=shells[0], r_org=shells[1],
                     tag="LAYERING", place=case["place"])
        self.gt["fin_anomalies"].append({"ref": id(r), "type": "RAPID_SEQUENCE"})
        for j, a in enumerate(accused):
            r = self.txn(inc + timedelta(hours=2 + j), cid, big * 0.3, "NEFT", "consultancy fee", s_org=shells[1],
                         receiver=a, tag="LAYERING", place=case["place"])
            self.gt["fin_anomalies"].append({"ref": id(r), "type": "RAPID_SEQUENCE"})
        # counter-example: the accountant legitimately receives a salary + a bonus from the same employer
        self.txn(inc - timedelta(days=5), cid, 185000, "NEFT", "annual performance bonus", s_org=employer,
                 receiver=accountant, tag="LEGIT_LARGE")
        self.gt["legit_large"].append({"case_id": cid, "person": accountant, "reason": "annual bonus"})
        narr = (f"Complainant {self._n(complainant, False)}, finance manager, reported that on {self._dt(inc)} an amount of "
                f"Rs {big:,} was released from the company account to {self.orgs[shells[0]]['name']} against invoices "
                f"later found to be fabricated. The invoices were introduced by {self._n(accused[0])} (mobile {self._ph(accused[0])}) "
                f"in association with {self._n(accused[1])}. Witness {self._n(witness, False)} stated that the accused persons "
                f"were seen together at the office premises days earlier. The company accountant "
                f"{self._n(accountant, False)} has been examined as a witness; no role has been attributed to him so far.")
        self._fir(case, narr, complainant, accused)

    def _scenario_extortion(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        case["place"] = self.rng.choice(places_in(case["city"], {"MARKET", "COMMERCIAL"}) or places_in(case["city"]))["id"]
        accused = self._accused_pids(case, self.rng.randint(1, 2))
        victim = self._pick_subject(case["city"], exclude=accused)
        neighbour = self._pick_subject(case["city"], exclude=accused + [victim])
        for a in accused: self._enroll(case, a, "ACCUSED")
        self._enroll(case, victim, "COMPLAINANT"); self._enroll(case, neighbour, "WITNESS")
        case["truth"] = {"involved": accused, "pattern": "threat messages, structured cash deposits"}
        lead = accused[0]
        for k, txt in enumerate(["Business is going well I hear. Time to contribute.",
                                 "2 lakh by Friday. Do not make me come to the shop.",
                                 "Last reminder. Deposit in the account I sent.",
                                 f"Account: {self._acct(lead)[0]}. Small amounts only."]):
            self.msg(lead, victim, inc - timedelta(days=6 - k * 1.5, hours=self.rng.uniform(0, 3)), cid, txt, tag="THREAT",
                     platform="WhatsApp")
        h = self.humans[self.persons[lead].hid]
        self._block(h, inc - timedelta(minutes=20), inc + timedelta(minutes=30), case["place"])
        self.ping(lead, inc, cid, "CELL_TOWER", case["place"], "AT_INCIDENT")
        self.ping(victim, inc + timedelta(minutes=5), cid, "GPS", case["place"], "AT_INCIDENT")
        for k in range(self.rng.randint(4, 6)):
            t = inc + timedelta(days=1 + k * 0.6, hours=self.rng.uniform(0, 4))
            r = self.txn(t, cid, self.rng.choice([45000, 48000, 49500, 40000]), "CASH_DEPOSIT", "cash deposit",
                         sender=victim, receiver=lead, tag="STRUCTURING")
            self.gt["fin_anomalies"].append({"ref": id(r), "type": "STRUCTURING"})
        if len(accused) > 1:
            self._burst(case, lead, accused[1], inc, n=5)
        narr = (f"The complainant {self._n(victim, False)}, shop owner at {PLACE[case['place']]['name']}, stated that he has been "
                f"receiving threatening WhatsApp messages from mobile {self._ph(lead)} demanding Rs 2,00,000. On {self._dt(inc)} "
                f"the accused {self._n(lead)} came to his shop and repeated the demand. Neighbouring shopkeeper "
                f"{self._n(neighbour, False)} witnessed the incident. Out of fear, the complainant deposited cash in instalments "
                f"in account {self._acct(lead)[0]}." + (f" The accused is suspected to act with {self._n(accused[1])}." if len(accused) > 1 else ""))
        self._fir(case, narr, victim, accused)

    def _scenario_narcotics(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        transit = places_in(case["city"], {"TRANSIT", "PUBLIC"}) or places_in("Mohali", {"PUBLIC"})
        case["place"] = self.rng.choice(transit)["id"]
        accused = self._accused_pids(case, self.rng.randint(2, 3))
        courier_kin = self.humans[self.persons[accused[-1]].hid].family
        relative = self.h2p[courier_kin[0]][0] if courier_kin else self._pick_subject()
        for a in accused: self._enroll(case, a, "ACCUSED")
        self._enroll(case, relative, "MENTIONED")
        # a seller at the same market/transit place: innocent repeated co-presence
        bystander = self._pick_subject(case["city"], exclude=accused + [relative])
        self._enroll(case, bystander, "MENTIONED")
        case["truth"] = {"involved": accused, "innocent": [relative, bystander],
                         "pattern": "repeated meetings at transit points, structured deposits"}
        for k in range(3):
            t = inc - timedelta(days=9 - k * 4, hours=self.rng.uniform(-2, 2))
            self._meeting(case, accused[:2], t, case["place"], tag="REPEATED_MEETING")
            self._burst(case, accused[0], accused[1], t - timedelta(hours=2), n=3, hours=1)
            self.msg(accused[0], accused[1], t - timedelta(hours=3), cid, "Parcel ready. Same place, same time.", tag="COORD")
            self.ping(bystander, t + timedelta(minutes=10), cid, "CHECKIN", case["place"], "INNOCENT_COPRESENCE")
        for k in range(self.rng.randint(4, 7)):
            t = inc - timedelta(days=self.rng.uniform(0, 14))
            r = self.txn(t, cid, self.rng.choice([42000, 46000, 48500, 49900]), "CASH_DEPOSIT", "cash deposit",
                         sender=accused[-1], receiver=accused[0], tag="STRUCTURING")
            self.gt["fin_anomalies"].append({"ref": id(r), "type": "STRUCTURING"})
        self.msg(accused[-1], relative, inc - timedelta(days=2), cid, "Will be late tonight, eat without me.", tag="INNOCENT")
        narr = (f"On {self._dt(inc)}, acting on secret information, a police party intercepted a vehicle near "
                f"{PLACE[case['place']]['name']}. {self._n(accused[0])} (mobile {self._ph(accused[0])}) and {self._n(accused[1])} "
                f"were apprehended; contraband was recovered. Interrogation revealed the role of "
                + (f"{self._n(accused[2])}, " if len(accused) > 2 else "")
                + f"who arranges deposits. {self._n(relative, False)}, a relative of one accused, was mentioned during questioning; "
                f"no material against her/him has emerged.")
        self._fir(case, narr, None, accused)

    def _scenario_vehicle_theft(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        case["place"] = self.rng.choice(places_in(case["city"]))["id"]
        accused = self._accused_pids(case, self.rng.randint(1, 2))
        owner = self._pick_subject(case["city"], exclude=accused)
        guard = self._pick_subject(case["city"], exclude=accused + [owner])
        for a in accused: self._enroll(case, a, "ACCUSED")
        self._enroll(case, owner, "COMPLAINANT"); self._enroll(case, guard, "WITNESS")
        case["truth"] = {"involved": accused, "pattern": "presence at incident place, call right after"}
        for a in accused:
            h = self.humans[self.persons[a].hid]
            self._block(h, inc - timedelta(minutes=25), inc + timedelta(minutes=15), case["place"])
            self.ping(a, inc - timedelta(minutes=10), cid, "CELL_TOWER", case["place"], "AT_INCIDENT")
        if len(accused) > 1:
            self.call(accused[0], accused[1], inc + timedelta(minutes=17), cid, dur=95, tag="AFTER_INCIDENT")
        buyer = self._pick_subject(exclude=accused + [owner, guard])
        self._enroll(case, buyer, "MENTIONED")
        self.txn(inc + timedelta(days=3), cid, self.rng.choice([65000, 82000, 120000]), "UPI", "vehicle sale",
                 sender=buyer, receiver=accused[0], tag="RESALE")
        vehicle = f"{self.rng.choice(['CH01', 'PB65', 'HR03', 'DL8C'])}-{self.rng.choice('ABCDEFGH')}{self.rng.choice('KLMNPRS')}-{self._digits(4)}"
        narr = (f"The complainant {self._n(owner, False)} reported that his vehicle {vehicle} parked at "
                f"{PLACE[case['place']]['name']} was stolen on {self._dt(inc)}. Security guard {self._n(guard, False)} saw "
                f"two persons near the vehicle. During investigation {self._n(accused[0])} was identified from CCTV stills"
                + (f" along with {self._n(accused[1])}." if len(accused) > 1 else ".")
                + f" The vehicle was allegedly sold to {self._n(buyer, False)}, whose role is under verification.")
        self._fir(case, narr, owner, accused)

    def _scenario_false_accusation(self, case):
        cid, inc = case["case_id"], case["incident_ts"]
        case["place"] = self.rng.choice(places_in(case["city"]))["id"]
        named = self._pick_subject(case["city"])
        complainant = self._pick_subject(case["city"], exclude=[named])
        self._enroll(case, named, "ACCUSED"); self._enroll(case, complainant, "COMPLAINANT")
        # the named person was demonstrably elsewhere (another city) at the time -> exculpatory evidence
        h = self.humans[self.persons[named].hid]
        far = self.rng.choice([c for c in ["Ludhiana", "Delhi", "Amritsar", "Ambala", "Gurugram"] if c != h.city])
        alibi = self.rng.choice(places_in(far))["id"]
        self._block(h, inc - timedelta(hours=5), inc + timedelta(hours=4), alibi)
        for k in range(4):
            self.ping(named, inc - timedelta(hours=3) + timedelta(minutes=90 * k), cid, "GPS", alibi, "ALIBI")
        self.txn(inc - timedelta(hours=1), cid, 1450, "CARD", "restaurant", sender=named, r_org="ORG-010", place=alibi, tag="ALIBI")
        case["truth"] = {"involved": [], "falsely_named": [named], "alibi_place": alibi,
                         "pattern": "named accused located in another city at incident time"}
        narr = (f"The complainant {self._n(complainant, False)} alleged that on {self._dt(inc)} at {PLACE[case['place']]['name']} "
                f"{self._n(named, False)} (mobile {self._ph(named)}) took Rs 3,00,000 as advance for a property deal and later refused "
                f"to execute the agreement. The accused, when contacted, denied meeting the complainant on that date and stated he "
                f"was in {far} for work. The matter appears to arise out of a prior business dispute between the parties.")
        self._fir(case, narr, complainant, [named])

    # ------------------------------------------------------------------ background
    def background(self):
        cfg = self.cfg
        subjects = [p for p in self.persons.values() if p.windows]
        n_windows = sum(len(p.windows) for p in subjects)
        per = lambda target, already: max(0, (target - already)) / max(1, n_windows)
        loc_n, cdr_n = per(cfg.n_location, len(self.rows["LOCATION"])), per(cfg.n_cdr, len(self.rows["CDR"]))
        soc_n, fin_n = per(cfg.n_social, len(self.rows["SOCIAL"])), per(cfg.n_transactions, len(self.rows["FIN"]))

        def contacts(p):
            h = self.humans[p.hid]
            hs = h.family * 3 + h.colleagues * 2 + h.friends
            return [self.h2p[x][0] for x in hs] or [self.rng.choice(list(self.persons))]

        def rnd(x):
            return int(x) + (1 if self.rng.random() < x - int(x) else 0)

        for p in subjects:
            h = self.humans[p.hid]
            cs = contacts(p)
            for cid, ws, we in p.windows:
                for _ in range(rnd(loc_n)):
                    t = self._rand_time(ws, we, (6, 24))
                    if t: self.ping(p.pid, t, cid)
                for _ in range(rnd(cdr_n)):
                    t = self._rand_time(ws, we)
                    if t: self.call(p.pid, self.rng.choice(cs), t, cid,
                                    call_type="SMS" if self.rng.random() < 0.12 else "VOICE")
                for _ in range(rnd(soc_n)):
                    t = self._rand_time(ws, we)
                    if t: self.msg(p.pid, self.rng.choice(cs), t, cid, self.rng.choice(W.INNOCENT_MESSAGES))
                # finances: salary + rent (repeated, legitimate), shopping, family transfers
                d = max(ws, self.t0).replace(day=1, hour=10, minute=0) + timedelta(days=31)
                while d < min(we, self.t_end):
                    if h.employer:
                        self.txn(d + timedelta(hours=self.rng.uniform(0, 6)), cid, self.rng.choice([28000, 35000, 52000, 76000, 120000]),
                                 "NEFT", "salary", s_org=h.employer, receiver=p.pid, tag="SALARY", place=h.work)
                    if h.family:
                        self.txn(d + timedelta(days=4, hours=2), cid, self.rng.choice([12000, 15000, 18000, 22000]), "UPI",
                                 "house rent", sender=p.pid, receiver=self.h2p[h.family[-1]][0], tag="RENT")
                    d = (d + timedelta(days=32)).replace(day=1)
                for _ in range(rnd(fin_n)):
                    t = self._rand_time(ws, we, (9, 22))
                    if not t: continue
                    r = self.rng.random()
                    if r < 0.55:
                        self.txn(t, cid, round(self.rng.lognormvariate(6.6, 0.9), 2), self.rng.choice(["UPI", "CARD"]),
                                 self.rng.choice(["groceries", "fuel", "food delivery", "pharmacy", "shopping"]),
                                 sender=p.pid, r_org=self.rng.choice(["ORG-010", "ORG-011", "ORG-012", "ORG-022"]))
                    elif r < 0.85:
                        self.txn(t, cid, round(self.rng.lognormvariate(7.8, 0.8), 2), "UPI",
                                 self.rng.choice(["family support", "split bill", "gift", "loan repayment"]),
                                 sender=p.pid, receiver=self.rng.choice(cs))
                    else:
                        self.txn(t, cid, round(self.rng.lognormvariate(7.2, 0.7), 2), "NETBANKING", "electricity bill",
                                 sender=p.pid, r_org="ORG-015")
            # occasional legitimate big purchase (counter-example for amount outliers)
            if self.rng.random() < 0.04 and p.windows:
                cid, ws, we = p.windows[0]
                t = self._rand_time(ws, we, (11, 16))
                if t:
                    self.txn(t, cid, self.rng.choice([850000, 1250000, 2100000]), "RTGS", "property booking - registered sale deed",
                             sender=p.pid, r_org="ORG-009", tag="LEGIT_LARGE")
                    self.gt["legit_large"].append({"case_id": cid, "person": p.pid, "reason": "property purchase"})

    def inject_travel_patterns(self):
        """Impossible travel (cloned SIM / shared handset / data error) + benign counter-examples."""
        subjects = [p for p in self.persons.values() if p.windows]
        for _ in range(self.cfg.n_impossible_travel):
            p = self.rng.choice(subjects)
            h = self.humans[p.hid]
            cid, ws, we = self.rng.choice(p.windows)
            t = self._rand_time(ws, we, (10, 20))
            if not t: continue
            base = self.position(h, t)
            if base is None: continue
            far = self.rng.choice([x for x in PLACE.values() if haversine_km(x["lat"], x["lon"], PLACE[base]["lat"], PLACE[base]["lon"]) > 250])
            r1 = self.ping(p.pid, t, cid, "GPS", base, "IMPOSSIBLE_TRAVEL_A", block=False)
            r2 = self.ping(p.pid, t + timedelta(minutes=self.rng.randint(20, 70)), cid, "CELL_TOWER", far["id"],
                           "IMPOSSIBLE_TRAVEL_B", block=False)
            self.gt["impossible_travel"].append({"person_id": p.pid, "refs": [id(r1), id(r2)],
                                                 "cause": self.rng.choice(["cloned_sim", "shared_handset", "data_error"])})
        # counter-example 1: cell-tower handover (few km in a minute but within tower precision)
        for _ in range(self.cfg.n_impossible_travel):
            p = self.rng.choice(subjects); h = self.humans[p.hid]
            cid, ws, we = self.rng.choice(p.windows)
            t = self._rand_time(ws, we, (10, 20))
            if not t or self.position(h, t) is None: continue
            pl = self.position(h, t)
            a = self.ping(p.pid, t, cid, "CELL_TOWER", pl, "HANDOVER", block=False)
            b = self.ping(p.pid, t + timedelta(seconds=50), cid, "CELL_TOWER", pl, "HANDOVER", block=False)
            if a and b:
                b["latitude"] = round(a["latitude"] + 0.04, 6); b["accuracy_m"] = 2500.0
                self.gt["benign_travel"].append({"person_id": p.pid, "reason": "cell handover within tower precision"})
        # counter-example 2: real flight Delhi -> Mumbai (fast but plausible by air)
        for _ in range(3):
            p = self.rng.choice(subjects); h = self.humans[p.hid]
            cid, ws, we = self.rng.choice(p.windows)
            t = self._rand_time(ws, we, (8, 12))
            if not t or any(abs((s0 - t).total_seconds()) < 3 * 86400 for s0, _ in h.busy): continue
            self._block(h, t - timedelta(hours=1), t + timedelta(hours=8), "LOC-MUM-01")
            h.overrides[-1] = (t, t + timedelta(minutes=40), "LOC-DEL-05")
            h.overrides.append((t + timedelta(hours=2, minutes=35), t + timedelta(hours=7), "LOC-MUM-03"))
            self.txn(t - timedelta(days=3), cid, 6450, "CARD", "air ticket DEL-BOM", sender=p.pid, r_org="ORG-014", tag="FLIGHT")
            self.ping(p.pid, t + timedelta(minutes=20), cid, "GPS", "LOC-DEL-05", "FLIGHT")
            self.ping(p.pid, t + timedelta(hours=2, minutes=45), cid, "GPS", "LOC-MUM-03", "FLIGHT")
            self.gt["benign_travel"].append({"person_id": p.pid, "reason": "commercial flight DEL-BOM (ticket purchase on record)"})

    def share_devices(self):
        """A family member's handset is also used by another person (common in households).
        Identity resolution must NOT merge these two people on the shared IMEI alone."""
        subjects = [p for p in self.persons.values() if p.windows and len(self.h2p[p.hid]) == 1]
        self.rng.shuffle(subjects)
        done = 0
        for p in subjects:
            h = self.humans[p.hid]
            fam = [f for f in h.family if len(self.h2p[f]) == 1]
            if not fam or done >= self.cfg.n_shared_devices:
                continue
            other = self.persons[self.h2p[fam[0]][0]]
            oh = self.humans[other.hid]
            oh.devices.append(h.devices[0])
            other.device_idx = len(oh.devices) - 1
            oh.home = h.home                      # same household: same night-time location, shared handset
            if not other.windows:
                case = self.cases[p.windows[0][0]]
                self._enroll(case, other.pid, "MENTIONED")
            self.gt["shared_devices"].append({"device": h.devices[0], "humans": [h.hid, oh.hid],
                                              "person_ids": [p.pid, other.pid]})
            done += 1

    def extra_statements(self):
        cases = list(self.cases.values())
        for c in cases:
            for w in c.get("late_witnesses", []):
                reg = c["registration_ts"] + timedelta(days=self.rng.uniform(2, 12))
                self._fir(c, f"Statement of witness {self._n(w, False)} (mobile {self._ph(w)}) recorded on "
                             f"{reg.strftime('%d/%m/%Y')}. The witness stated that they were present near "
                             f"{PLACE[c['place']]['name']} on the day of the incident and noticed a commotion, "
                             f"but could not identify anyone.", None, [], kind="WITNESS_STATEMENT", reg=reg,
                          reliability="MEDIUM")
        for _ in range(self.cfg.n_fir_extra_statements):
            c = self.rng.choice(cases)
            roles = c["roles"]
            wit = [p for p, r in roles.items() if "WITNESS" in r or "VICTIM" in r or "COMPLAINANT" in r]
            acc = [p for p, r in roles.items() if "ACCUSED" in r]
            if not wit or not acc: continue
            w, a = self.rng.choice(wit), self.rng.choice(acc)
            reg = c["registration_ts"] + timedelta(days=self.rng.uniform(1, 25))
            templates = [
                f"Supplementary statement of witness {self._n(w, False)} recorded on {reg.strftime('%d/%m/%Y')}. The witness stated "
                f"that {self._n(a)} was known to him and had called him from {self._ph(a)} a few days before the incident.",
                f"Statement of {self._n(w, False)}: I do not personally know {self._n(a)}. I only heard about the incident from others.",
                f"Further investigation: call detail records of {self._ph(a)} (used by {self._n(a)}) have been requisitioned. "
                f"Statement of {self._n(w, False)} recorded.",
            ]
            self._fir(c, self.rng.choice(templates), w if "COMPLAINANT" in roles[w] else None, [a],
                      kind="SUPPLEMENTARY_STATEMENT", reg=reg, reliability="MEDIUM")

    # ------------------------------------------------------------------ criminal history (6th source)
    def criminal_history(self):
        """Prior records from a separate records system (no KRONOS person IDs). Linking them to current
        profiles is the job of the criminal-history linkage engine. Includes traps: namesakes where only
        one bearer has a record, and same-name records of people who are not in the current data."""
        rows = []
        disp = [d for d, _ in W.DISPOSITIONS]; dw = [w for _, w in W.DISPOSITIONS]

        def record(name, father, city, phone, aliases="", minor=False, birth_year=None, hid=None, kind="TRUE"):
            off, sec, mo = self.rng.choice(W.MINOR_OFFENCES if minor else W.HISTORY_OFFENCES)
            yr = self.rng.randint(2015, 2024)
            stn_city = city if W.CITIES.get(city, (None, None, []))[2] else self.rng.choice(W.CASE_CITIES)
            district, _, stations = W.CITIES[stn_city]
            addr_pool = places_in(city, {"RESIDENTIAL"}) or places_in(city)
            rows.append(dict(
                record_type=self.rng.choice(["ARREST", "CHARGESHEET", "COURT_RECORD"]),
                source_system=self.rng.choice(W.HISTORY_SOURCES), full_name=name, alias_names=aliases,
                father_name=father, birth_year=birth_year or "", address=self.rng.choice(addr_pool)["name"] if addr_pool else city,
                phone_at_record=phone or "", fir_reference=f"FIR {self.rng.randint(11, 480)}/{yr} {self.rng.choice(stations)}",
                offence_category=off, sections=sec, police_station=self.rng.choice(stations), district=district,
                record_date=f"{yr}-{self.rng.randint(1, 12):02d}-{self.rng.randint(1, 28):02d}",
                disposition=self.rng.choices(["ACQUITTED", "DISCHARGED", "COMPOUNDED"] if minor else disp,
                                             [0.5, 0.2, 0.3] if minor else dw)[0],
                modus_operandi=mo, source_reliability=self.rng.choice(["HIGH", "HIGH", "MEDIUM"]), _hid=hid, _kind=kind))

        # 1) repeat offenders (incl. alias and burner humans): 1-3 prior records each, recorded under the real
        #    identity; current address/phone only sometimes match (people move and change numbers)
        for hid in self.repeat_pool:
            h = self.humans[hid]
            recs = self.h2p[hid]
            alias = ";".join(self.persons[r].name for r in recs[1:]) if len(recs) > 1 and not h.burner and self.rng.random() < 0.6 else ""
            for _ in range(self.rng.randint(1, 3)):
                record(h.name, h.father, h.city if self.rng.random() < 0.8 else self.rng.choice(W.CASE_CITIES),
                       h.phones[0] if self.rng.random() < 0.45 else self._phone(), aliases=alias,
                       birth_year=h.birth_year if self.rng.random() < 0.7 else None, hid=hid)
        # 2) other people with minor / old records (often acquitted) — context only, must not drive suspicion
        others = [p for p in self.persons.values() if p.windows and len(self.h2p[p.hid]) == 1 and p.hid not in self.repeat_pool]
        for p in self.rng.sample(others, min(self.cfg.n_history_other, len(others))):
            h = self.humans[p.hid]
            record(h.name, h.father, h.city, h.phones[0] if self.rng.random() < 0.5 else self._phone(),
                   minor=self.rng.random() < 0.6, birth_year=h.birth_year if self.rng.random() < 0.6 else None, hid=p.hid)
        # 3) namesake trap: only ONE of the two same-name people has a record
        for ns in self.gt["namesakes"]:
            h = self.humans[self.persons[ns["person_ids"][0]].hid]
            record(h.name, h.father, h.city, h.phones[0] if self.rng.random() < 0.5 else self._phone(),
                   birth_year=h.birth_year, hid=h.hid, kind="NAMESAKE_TRAP")
        # 4) people not in the current data; half share the full name of a current subject (same-name strangers)
        subjects = [p for p in self.persons.values() if p.windows]
        for i in range(self.cfg.n_history_noise):
            if i % 2 == 0:
                name = self.rng.choice(subjects).name
                kind = "SAME_NAME_STRANGER"
            else:
                name = self._unique_name("M"); kind = "NOISE"
            record(name, f"{self.rng.choice(W.FATHER_FIRST)} {name.split()[-1]}", self.rng.choice(W.CASE_CITIES),
                   self._phone(), birth_year=self.rng.randint(1960, 2003), hid=None, kind=kind)
        rows.sort(key=lambda r: r["record_date"])
        for i, r in enumerate(rows, 1):
            r["record_id"] = f"HIST{i:06d}"; r["source_record_id"] = f"SRC-HIST{i:06d}"; r["evidence_id"] = f"EVD-HIST{i:06d}"
            self.gt["history"].append({"history_id": r["record_id"], "evidence_id": r["evidence_id"], "human": r["_hid"],
                                       "kind": r["_kind"]})
        self.rows["HISTORY"] = rows

    # ------------------------------------------------------------------ output
    def run(self):
        self.build_population()
        self.build_cases()
        self.share_devices()
        self.inject_travel_patterns()
        self.background()
        self.extra_statements()
        self.criminal_history()
        return self.write()

    def _ids(self, key, prefix):
        rows = sorted(self.rows[key], key=lambda r: r.get("timestamp") or r.get("registration_ts"))
        for i, r in enumerate(rows, 1):
            r["record_id"] = f"{prefix}{i:06d}"
            r["source_record_id"] = f"SRC-{prefix}{i:06d}"
            r["evidence_id"] = f"EVD-{prefix}{i:06d}"
        return rows

    def write(self):
        out = Path(self.cfg.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ref2id = {}

        def fmt(t, f):
            return t.strftime(f) if isinstance(t, datetime) else t

        fir = self._ids("FIR", "FIR")
        cdr = self._ids("CDR", "CDR")
        loc = self._ids("LOCATION", "LOC")
        fin = self._ids("FIN", "TXN")
        soc = self._ids("SOCIAL", "MSG")
        for rows in (fir, cdr, loc, fin, soc):
            for r in rows:
                ref2id[id(r)] = r["evidence_id"]
        # FIR numbers: one per case for the primary FIR
        fir_no = {}
        for r in fir:
            c = self.cases[r["case_id"]]
            if r["record_type"] == "FIR":
                fir_no[r["case_id"]] = f"FIR/{c['police_station'].replace('PS ', '').replace(' ', '')[:10].upper()}/{c['incident_ts'].year}/{int(r['case_id'][4:]):04d}"
            r["fir_number"] = fir_no.get(r["case_id"], "")
        specs = {
            "FIR.csv": (fir, ["fir_number", "record_id", "case_id", "record_type", "agency_id", "police_station", "district",
                              ("registration_date", lambda r: fmt(r["registration_ts"], "%Y-%m-%d")),
                              ("registration_time", lambda r: fmt(r["registration_ts"], "%H:%M")),
                              ("incident_datetime", lambda r: fmt(r["incident_ts"], "%d-%m-%Y %H:%M")),
                              "offence_category", "sections", "complainant_person_id", "complainant_name",
                              "accused_person_ids", "incident_location", "incident_lat", "incident_lon", "narrative",
                              "source_reliability", "evidence_id", "source_record_id"]),
            "CDR.csv": (cdr, ["record_id", "case_id", "caller_person_id", "caller_name", "caller_number", "receiver_person_id",
                              "receiver_name", "receiver_number",
                              ("call_date", lambda r: fmt(r["timestamp"], "%d-%m-%Y")),
                              ("call_time", lambda r: fmt(r["timestamp"], "%H:%M:%S")),
                              "duration_sec", "call_type", "call_status", "imei", "imsi", "cell_tower_id", "tower_lat",
                              "tower_lon", "tower_location", "source_reliability", "evidence_id", "source_record_id"]),
            "LOCATION.csv": (loc, ["record_id", "case_id", "person_id", "phone_number", "device_id",
                                   ("timestamp", lambda r: fmt(r["timestamp"], "%Y-%m-%d %H:%M:%S")),
                                   "latitude", "longitude", "accuracy_m", "location_name", "location_type", "source_type",
                                   "source_reliability", "evidence_id", "source_record_id"]),
            "FINANCIAL_TRANSACTIONS.csv": (fin, ["record_id", "case_id",
                                                 ("txn_datetime", lambda r: fmt(r["timestamp"], "%Y-%m-%dT%H:%M:%S")),
                                                 "sender_person_id", "sender_name", "sender_account", "sender_bank",
                                                 "sender_org_id", "receiver_person_id", "receiver_name", "receiver_account",
                                                 "receiver_bank", "receiver_org_id", "amount", "currency", "channel",
                                                 "purpose", "status", "location_name", "latitude", "longitude",
                                                 "source_reliability", "evidence_id", "source_record_id"]),
            "SOCIAL_MEDIA_CHATS.csv": (soc, ["record_id", "case_id", "platform",
                                             ("timestamp", lambda r: fmt(r["timestamp"], "%d/%m/%Y %H:%M")),
                                             "sender_person_id", "sender_name", "sender_handle", "sender_phone",
                                             "receiver_person_id", "receiver_name", "receiver_handle", "receiver_phone",
                                             "message_text", "device_id", "latitude", "longitude", "source_reliability",
                                             "evidence_id", "source_record_id"]),
            "CRIMINAL_HISTORY.csv": (self.rows["HISTORY"], ["record_id", "record_type", "source_system", "full_name",
                                                         "alias_names", "father_name", "birth_year", "address",
                                                         "phone_at_record", "fir_reference", "offence_category",
                                                         "sections", "police_station", "district", "record_date",
                                                         "disposition", "modus_operandi", "source_reliability",
                                                         "evidence_id", "source_record_id"]),
        }
        rendered = {}
        for fname, (rows, cols) in specs.items():
            out_rows = []
            for r in rows:
                o = {}
                for c in cols:
                    if isinstance(c, tuple):
                        o[c[0]] = c[1](r)
                    else:
                        v = r.get(c)
                        o[c] = "" if v is None else v
                o["_ref"] = id(r)
                out_rows.append(o)
            rendered[fname] = out_rows
        # inject a small number of malformed values (documented in ground truth)
        mal = {"CDR.csv": ["call_date", "caller_number"], "LOCATION.csv": ["timestamp", "latitude", "person_id"],
               "FINANCIAL_TRANSACTIONS.csv": ["txn_datetime", "amount"], "SOCIAL_MEDIA_CHATS.csv": ["timestamp"]}
        for fname, fields in mal.items():
            rows = rendered[fname]
            for r in self.rng.sample(rows, int(len(rows) * self.cfg.malformed_rate)):
                f = self.rng.choice(fields)
                r[f] = {"call_date": "31-02-2025", "caller_number": "N/A", "timestamp": "2025-13-45 25:61:00",
                        "latitude": "999.0", "person_id": "", "txn_datetime": "not-a-date", "amount": "-abc"}[f]
                self.gt["malformed"].append({"file": fname, "source_record_id": r["source_record_id"], "field": f})
        for fname, rows in rendered.items():
            cols = [c[0] if isinstance(c, tuple) else c for c in specs[fname][1]]
            with open(out / fname, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        # ground truth (evaluation only)
        gt = {k: v for k, v in self.gt.items()}
        for k in ("fin_anomalies",):
            gt[k] = [{"evidence_id": ref2id.get(x["ref"]), "type": x["type"]} for x in gt.get(k, []) if ref2id.get(x["ref"])]
        gt["impossible_travel"] = [{"person_id": x["person_id"], "evidence_ids": [ref2id.get(r) for r in x["refs"]],
                                    "cause": x["cause"]} for x in gt.get("impossible_travel", [])]
        gt["person_to_human"] = {p.pid: p.hid for p in self.persons.values()}
        gt["humans"] = {h.hid: {"name": h.name, "city": h.city, "phones": h.phones, "devices": h.devices,
                                "father": h.father, "birth_year": h.birth_year, "burner": h.burner,
                                "person_ids": self.h2p[h.hid]} for h in self.humans.values()}
        gt["cases_meta"] = {cid: {"scenario": c["scenario"], "title": c["title"], "agency_id": c["agency_id"],
                                  "lead_investigator": c["lead_investigator"], "place": c["place"]}
                            for cid, c in self.cases.items()}
        gt["config"] = asdict(self.cfg)
        gt["counts"] = {f: len(r) for f, r in rendered.items()}
        (out / "ground_truth.json").write_text(json.dumps(gt, indent=1, default=str))
        # case metadata that a real system would hold in its case-management module (not analytics truth)
        (out / "CASE_REGISTER.csv").write_text(
            "case_id,title,agency_id,lead_investigator\n" + "".join(
                f'{cid},"{c["title"]}",{c["agency_id"]},{c["lead_investigator"]}\n' for cid, c in self.cases.items()))
        return gt["counts"]


def generate(cfg: SynthConfig | None = None) -> dict:
    return Generator(cfg or SynthConfig()).run()
