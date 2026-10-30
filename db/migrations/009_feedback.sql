create table feedback (
  id bigserial primary key,
  source text not null check (source in ('customer', 'admin')),
  agent_code text not null references agent_profiles(agent_code) on delete cascade,
  team text references teams(code),
  category text,
  rating smallint check (rating between 1 and 5),
  body text not null,
  author_id bigint references users(id) on delete set null,
  author_name text not null,
  seed_key text unique,
  created_at timestamptz not null default now(),
  seen_at timestamptz,
  check (source = 'admin' or rating is not null)
);

create index feedback_by_agent on feedback (agent_code, created_at desc);
create index feedback_by_time on feedback (created_at desc);
