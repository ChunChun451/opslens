from __future__ import annotations

import os

import pandas as pd
from argon2 import PasswordHasher

from opslens import store
from opslens.config import load_config, load_env_file, project_path

AGENTS_CSV = project_path("data/generated/agents.csv")
DEMO_DOMAIN = "opslens.demo"
hasher = PasswordHasher()


def demo_password() -> str:
    load_env_file()
    return os.environ.get("DEMO_PASSWORD", "opslens-demo")


def split(cell) -> list[str]:
    return [x for x in str(cell).split("|") if x and x != "nan"]


def seed(conn) -> dict[str, int]:
    roster = load_config("roster")
    teams = roster["teams"]
    with conn.transaction():
        for code, team in teams.items():
            conn.execute("insert into teams (code, name) values (%s, %s) on conflict (code) do update set name = excluded.name",
                         (code, team["name"]))
        agents = pd.read_csv(AGENTS_CSV)
        for a in agents.itertuples():
            conn.execute(
                "insert into agent_profiles (agent_code, name, team, skills, languages, shift_start_hour, shift_hours, days_off, max_concurrent) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict (agent_code) do update set name = excluded.name, team = excluded.team, "
                "skills = excluded.skills, languages = excluded.languages, shift_start_hour = excluded.shift_start_hour, "
                "shift_hours = excluded.shift_hours, days_off = excluded.days_off, max_concurrent = excluded.max_concurrent",
                (a.agent_id, a.name, a.team, split(a.skills), split(a.languages), int(a.shift_start_hour), int(a.shift_hours),
                 [int(d) for d in split(a.days_off)], int(a.max_concurrent)))
        password = hasher.hash(demo_password())
        users = [(f"admin@{DEMO_DOMAIN}", "Ops admin", "admin", None, None)]
        users += [(f"lead.{code.lower()}@{DEMO_DOMAIN}", f"Team {code} lead", "lead", code, None) for code in teams]
        users += [(f"{a.agent_id.lower()}@{DEMO_DOMAIN}", a.name, "agent", a.team, a.agent_id) for a in agents.itertuples()]
        for email, name, role, team, agent_code in users:
            conn.execute(
                "insert into users (email, name, role, team, agent_code, password_hash) values (%s, %s, %s, %s, %s, %s) "
                "on conflict (email) do update set name = excluded.name, role = excluded.role, team = excluded.team, "
                "agent_code = excluded.agent_code, password_hash = excluded.password_hash",
                (email, name, role, team, agent_code, password))
    return {"teams": len(teams), "agents": len(agents), "users": len(users)}


def main() -> int:
    from datetime import date
    applied = store.migrate()
    parts = store.ensure_partitions(date.today().replace(day=1), months=3)
    with store.connection() as conn:
        counts = seed(conn)
    print(f"migrations applied: {applied or 'none (up to date)'}; partitions: {len(parts)}; seeded {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
