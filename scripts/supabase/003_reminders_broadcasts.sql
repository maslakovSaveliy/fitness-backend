-- user_reminders, broadcasts
-- Apply manually in Supabase SQL editor.

create table if not exists user_reminders (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references users(id) on delete cascade,
  enabled boolean not null default true,
  timezone text,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  unique(user_id)
);

create index if not exists idx_user_reminders_user_id on user_reminders(user_id);

create or replace function update_user_reminders_updated_at()
returns trigger as $$
begin
  new.updated_at = timezone('utc'::text, now());
  return new;
end;
$$ language 'plpgsql';

drop trigger if exists trg_update_user_reminders_updated_at on user_reminders;
create trigger trg_update_user_reminders_updated_at
  before update on user_reminders
  for each row execute function update_user_reminders_updated_at();

create table if not exists broadcasts (
  id uuid default gen_random_uuid() primary key,
  created_by uuid references users(id) on delete set null,
  text text not null,
  audience text not null default 'all',
  status text not null default 'created',
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index if not exists idx_broadcasts_created_by on broadcasts(created_by);


