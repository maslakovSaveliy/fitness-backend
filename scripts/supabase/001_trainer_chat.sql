-- trainer_chat_sessions / trainer_chat_messages
-- Apply manually in Supabase SQL editor.
--
-- В проде тип users.id может быть uuid или text. Чтобы FK гарантированно создавался,
-- определяем тип динамически из pg_catalog и создаём таблицы через EXECUTE.

do $$
declare
  users_id_type text;
begin
  select a.atttypid::regtype::text
    into users_id_type
  from pg_attribute a
  join pg_class c on c.oid = a.attrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relname = 'users'
    and a.attname = 'id'
    and a.attnum > 0
    and not a.attisdropped;

  if users_id_type is null then
    raise exception 'Cannot detect public.users.id type';
  end if;

  if to_regclass('public.trainer_chat_sessions') is null then
    execute format($f$
      create table public.trainer_chat_sessions (
        id uuid default gen_random_uuid() primary key,
        user_id %s not null,
        status text not null default 'active',
        original_workout_text text,
        updated_workout_text text,
        created_at timestamp with time zone default timezone('utc'::text, now()) not null
      );
    $f$, users_id_type);

    execute 'alter table public.trainer_chat_sessions add constraint trainer_chat_sessions_user_id_fkey foreign key (user_id) references public.users(id) on delete cascade';
  end if;

  create index if not exists idx_trainer_chat_sessions_user_id
    on public.trainer_chat_sessions(user_id);

  if to_regclass('public.trainer_chat_messages') is null then
    execute $f$
      create table public.trainer_chat_messages (
        id uuid default gen_random_uuid() primary key,
        session_id uuid references public.trainer_chat_sessions(id) on delete cascade,
        role text not null check (role in ('user', 'assistant')),
        content text not null,
        created_at timestamp with time zone default timezone('utc'::text, now()) not null
      );
    $f$;
  end if;

  create index if not exists idx_trainer_chat_messages_session_id
    on public.trainer_chat_messages(session_id);
end $$;


