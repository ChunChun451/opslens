do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'vector') then
    create extension if not exists vector;
    alter table kb_articles alter column embedding type vector(768) using embedding::vector;
    alter table ticket_embeddings alter column embedding type vector(768) using embedding::vector;
    create index if not exists ticket_embeddings_hnsw on ticket_embeddings using hnsw (embedding vector_cosine_ops);
    create index if not exists kb_articles_hnsw on kb_articles using hnsw (embedding vector_cosine_ops);
  end if;
end $$;
