-- v1 schema for Supabase Postgres
create extension if not exists "pgcrypto";

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  tg_user_id bigint unique not null,
  username text,
  display_name text,
  is_admin boolean default false,
  created_at timestamptz default now()
);

create table if not exists groups (
  id uuid primary key default gen_random_uuid(),
  tg_group_id bigint unique not null,
  title text,
  active boolean default true,
  created_at timestamptz default now()
);

create table if not exists memberships (
  user_id uuid references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  primary key (user_id, group_id)
);

create table if not exists reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  title text not null,
  time_of_day time,
  weekdays int[] default '{1,2,3,4,5,6,7}',
  active boolean default true,
  created_at timestamptz default now()
);

create table if not exists daily_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  for_date date not null,
  title text not null,
  time_of_day time,
  done boolean default false,
  created_at timestamptz default now()
);

create table if not exists settings (
  key text primary key,
  value text
);

create table if not exists conversation_state (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  chat_id bigint not null,
  state jsonb not null,
  expires_at timestamptz not null,
  created_at timestamptz default now()
);

create index if not exists idx_daily_tasks_date_user on daily_tasks(for_date, user_id);
create index if not exists idx_reminders_user on reminders(user_id);
create index if not exists idx_reminders_group on reminders(group_id);
