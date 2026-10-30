create materialized view team_daily as
select team, (created_at at time zone 'Asia/Kolkata')::date as day, count(*) as tickets,
       count(*) filter (where breached) as missed, count(*) filter (where priority = 'P1') as live_orders,
       count(*) filter (where priority = 'P1' and breached) as live_orders_missed
from tickets
group by 1, 2;

create unique index team_daily_key on team_daily (team, day);
