-- trainer_chat_sessions / trainer_chat_messages
-- Apply manually in Supabase SQL editor.

create table if not exists trainer_chat_sessions (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references users(id) on delete cascade,
  status text not null default 'active',
  original_workout_text text,
  updated_workout_text text,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index if not exists idx_trainer_chat_sessions_user_id
  on trainer_chat_sessions(user_id);

create table if not exists trainer_chat_messages (
  id uuid default gen_random_uuid() primary key,
  session_id uuid references trainer_chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index if not exists idx_trainer_chat_messages_session_id
  on trainer_chat_messages(session_id);


