create table ticket_messages (
  id bigserial primary key,
  ticket_id text not null references tickets(id) on delete cascade,
  author_id bigint references users(id) on delete set null,
  author_name text not null,
  author_role text not null,
  kind text not null check (kind in ('public', 'internal')),
  body text not null,
  at timestamptz not null default now()
);

create index ticket_messages_by_ticket on ticket_messages (ticket_id, at);

create table plan_choices (
  item_id text primary key,
  chosen_by bigint references users(id) on delete set null,
  chosen_at timestamptz not null default now()
);

create table plan_runs (
  id bigserial primary key,
  day int not null,
  items text[] not null,
  result jsonb not null,
  run_by bigint references users(id) on delete set null,
  at timestamptz not null default now()
);
