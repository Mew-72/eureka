-- Phase 1 schema. Run once in the Supabase SQL editor.
create extension if not exists vector with schema extensions;

insert into storage.buckets (id, name, public, file_size_limit)
values ('face-evidence', 'face-evidence', false, 15728640)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit;

create table if not exists public.face_records (
    id uuid primary key,
    created_at timestamptz not null default timezone('utc', now()),
    fingerprint_timestamp text not null,
    probe_storage_path text not null,
    content_storage_path text,
    fingerprint_storage_path text not null,
    fingerprint_image_source text not null
        check (fingerprint_image_source in ('probe', 'matched')),
    face_embedding extensions.vector(128) not null,
    sha256_hash text not null check (sha256_hash ~ '^[0-9a-f]{64}$'),
    matched_url text not null,
    matched_image_url text,
    match_source text not null,
    match_type text not null,
    match_score double precision not null check (match_score between 0 and 1),
    page_title text,
    caption text,
    platform text,
    published_at text,
    vision_result_count integer not null check (vision_result_count >= 1),
    chain_tx_hash text,
    metadata jsonb not null default '{}'::jsonb
);

alter table public.face_records enable row level security;

comment on column public.face_records.fingerprint_timestamp is
    'Exact timestamp string included in SHA-256; do not normalize or rewrite.';
comment on column public.face_records.face_embedding is
    '128-d face vector; embedding model/version is recorded in metadata.';
comment on column public.face_records.match_score is
    'Provider relevance/ranking score, not face-identification confidence.';
comment on column public.face_records.chain_tx_hash is
    'Reserved for the Phase 3 blockchain integration.';
