create table proposals (
  id bigserial primary key,
  run_id bigint references agent_runs(id) on delete set null,
  kind text not null check (kind in ('reassign', 'note')),
  team text,
  ticket_id text,
  agent_code text,
  title text not null,
  why text,
  evidence jsonb,
  status text not null default 'waiting' check (status in ('waiting', 'approved', 'rejected', 'failed', 'expired')),
  result jsonb,
  decided_by bigint references users(id),
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create index proposals_waiting on proposals (team, created_at desc) where status = 'waiting';
create index agent_runs_recent on agent_runs (started_at desc);
create index agent_runs_by_ticket on agent_runs (ticket_id, agent) where ticket_id is not null;

alter table agent_runs add column requested_by bigint references users(id);
alter table tickets add column ai_urgency text;
create unique index kb_articles_title on kb_articles (title);
alter table kb_articles add column category text;
