create table teams (
  code text primary key,
  name text not null
);

create table agent_profiles (
  agent_code text primary key,
  name text not null,
  team text not null references teams(code),
  skills text[] not null,
  languages text[] not null,
  shift_start_hour int not null,
  shift_hours int not null,
  days_off int[] not null default '{}',
  max_concurrent int not null default 1
);

create table users (
  id bigserial primary key,
  email text not null unique,
  name text not null,
  role text not null check (role in ('admin', 'lead', 'agent')),
  team text references teams(code),
  agent_code text unique references agent_profiles(agent_code),
  password_hash text not null,
  created_at timestamptz not null default now()
);

create table tickets (
  id text primary key,
  day int not null,
  created_at timestamptz not null,
  channel text,
  priority text not null,
  language text,
  category text,
  customer_tier text,
  order_value_inr numeric,
  restaurant text,
  body text not null,
  status text not null check (status in ('open', 'in_progress', 'solved')),
  assignee text references agent_profiles(agent_code),
  team text references teams(code),
  sla_due_at timestamptz not null,
  assigned_at timestamptz,
  solved_at timestamptz,
  breached boolean,
  risk numeric,
  risk_reasons jsonb,
  assign_reason text,
  ai_category text,
  ai_summary text,
  updated_at timestamptz not null default now()
);

create index tickets_open_by_team on tickets (team, sla_due_at) where status <> 'solved';
create index tickets_by_assignee on tickets (assignee, status);
create index tickets_by_created on tickets (created_at);

create table ticket_events (
  id bigserial,
  ticket_id text not null,
  at timestamptz not null,
  kind text not null,
  actor text,
  detail jsonb,
  primary key (id, at),
  unique (ticket_id, kind, at)
) partition by range (at);

create table decisions (
  id bigserial,
  at timestamptz not null,
  ticket_id text not null,
  agent_code text not null,
  reason text,
  rescue_value numeric,
  policy text not null default 'opslens',
  primary key (id, at),
  unique (ticket_id, agent_code, at)
) partition by range (at);

create table risk_scores (
  ticket_id text not null,
  at timestamptz not null,
  risk numeric not null,
  reasons jsonb,
  primary key (ticket_id, at)
) partition by range (at);

create table recommendations (
  id text primary key,
  title text not null,
  owner text,
  status text not null default 'open' check (status in ('open', 'accepted', 'overridden')),
  reason text,
  evidence jsonb,
  decided_by bigint references users(id),
  decided_at timestamptz
);

create table agent_runs (
  id bigserial primary key,
  agent text not null,
  trigger text not null,
  ticket_id text,
  status text not null default 'running' check (status in ('running', 'done', 'failed', 'needs_approval')),
  summary text,
  output jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table agent_steps (
  run_id bigint not null references agent_runs(id) on delete cascade,
  n int not null,
  kind text not null check (kind in ('tool_call', 'tool_result', 'answer', 'error')),
  tool text,
  payload jsonb,
  at timestamptz not null default now(),
  primary key (run_id, n)
);

create table analysis_jobs (
  id text primary key,
  file_name text not null,
  status text not null,
  result jsonb,
  created_at timestamptz not null default now()
);

create table kb_articles (
  id bigserial primary key,
  title text not null,
  body text not null,
  embedding real[]
);

create table ticket_embeddings (
  ticket_id text primary key references tickets(id) on delete cascade,
  embedding real[] not null
);

create table job_queue (
  id bigserial primary key,
  queue text not null,
  payload jsonb not null,
  status text not null default 'ready' check (status in ('ready', 'taken', 'done', 'failed')),
  attempts int not null default 0,
  created_at timestamptz not null default now(),
  taken_at timestamptz
);

create index job_queue_ready on job_queue (queue, id) where status = 'ready';

create materialized view team_hourly as
  select team, date_trunc('hour', created_at) as hour, count(*) as created,
         count(*) filter (where breached) as breached,
         count(*) filter (where status = 'solved') as solved
  from tickets
  group by team, date_trunc('hour', created_at);

create unique index team_hourly_key on team_hourly (team, hour);
