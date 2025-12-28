-- feedback table + role on users
-- Apply manually in Supabase SQL editor.

alter table users
add column if not exists role text;

create table if not exists feedback (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references users(id) on delete cascade,
  category text,
  message text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index if not exists idx_feedback_user_id on feedback(user_id);


