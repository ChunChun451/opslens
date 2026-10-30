create table rag_chunks (
  id bigserial primary key,
  source text not null,
  ref text not null unique,
  title text not null,
  body text not null,
  link text,
  card text,
  embedding real[],
  built_at timestamptz not null default now()
);

create index rag_chunks_by_source on rag_chunks (source);
