\pset pager off
\echo
\echo === 1. Which server, where its files are, how big ===
select version();
select current_database() as database, inet_server_port() as port, current_setting('data_directory') as data_folder,
       pg_size_pretty(pg_database_size(current_database())) as size;
select datname as all_databases, pg_size_pretty(pg_database_size(datname)) as size from pg_database where not datistemplate order by 1;

\echo
\echo === 2. Every table, with its row count ===
select c.relname as table_name,
       case c.relkind when 'p' then 'partitioned by month' when 'm' then 'pre-counted view' else 'table' end as kind,
       (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %I', c.relname), false, true, '')))[1]::text::bigint as rows
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p', 'm') and not c.relispartition
order by rows desc;

\echo
\echo === 3. The history is split into one table per month ===
select inhparent::regclass as parent, inhrelid::regclass as month_partition from pg_inherits
where inhparent in ('ticket_events'::regclass, 'decisions'::regclass, 'risk_scores'::regclass) order by 1, 2;

\echo
\echo === 4. The small index that only covers unsolved tickets ===
select indexname, indexdef from pg_indexes where indexname = 'tickets_open_by_team';

\echo
\echo === 5. Live tickets right now, by team and status ===
select team, status, count(*) as tickets from tickets group by 1, 2 order by 1, 2;

\echo
\echo === 6. The latest things that happened to tickets ===
select at, ticket_id, kind, actor from ticket_events order by at desc limit 8;

\echo
\echo === 7. Why OpsLens gave a ticket to an agent ===
select at, ticket_id, agent_code, left(reason, 90) as reason from decisions order by at desc limit 5;

\echo
\echo === 8. Every AI step is recorded ===
select r.id as run, r.agent, r.status, s.n as step, s.kind, s.tool from agent_runs r join agent_steps s on s.run_id = r.id
where r.id = (select max(run_id) from agent_steps) order by s.n;

\echo
\echo === 9. Customer feedback (entered by hand) and admin notes ===
select f.source, p.name as agent, f.team, f.rating, left(f.body, 70) as said, f.seen_at is null as unread
from feedback f join agent_profiles p on p.agent_code = f.agent_code order by f.created_at desc limit 8;
select team, round(avg(rating), 1) as customer_rating, count(*) as reviews from feedback where source = 'customer' group by team order by 2;

\echo
\echo === 10. The RAG library: pieces by source ===
select source, count(*) as pieces, count(embedding) as with_meaning_vector from rag_chunks group by 1 order by 2 desc;

\echo
\echo === 11. Passwords and sessions are never stored as they are ===
select email, role, left(password_hash, 30) || '...' as password_is_stored_as from users order by id limit 3;
select left(token_hash, 16) || '...' as session_is_stored_as_sha256, expires_at from sessions order by created_at desc limit 2;
