alter table agent_runs drop constraint agent_runs_requested_by_fkey,
  add constraint agent_runs_requested_by_fkey foreign key (requested_by) references users(id) on delete set null;

alter table proposals drop constraint proposals_decided_by_fkey,
  add constraint proposals_decided_by_fkey foreign key (decided_by) references users(id) on delete set null;

alter table recommendations drop constraint recommendations_decided_by_fkey,
  add constraint recommendations_decided_by_fkey foreign key (decided_by) references users(id) on delete set null;
