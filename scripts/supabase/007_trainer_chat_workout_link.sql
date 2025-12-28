-- Link trainer chat sessions to a draft workout and store jsonb snapshots
-- Apply manually in Supabase SQL editor.
--
-- В проде тип workouts.id может быть uuid или text. Подхватываем тип динамически.

do $$
declare
  workouts_id_type text;
begin
  select a.atttypid::regtype::text
    into workouts_id_type
  from pg_attribute a
  join pg_class c on c.oid = a.attrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relname = 'workouts'
    and a.attname = 'id'
    and a.attnum > 0
    and not a.attisdropped;

  if workouts_id_type is null then
    raise exception 'Cannot detect public.workouts.id type';
  end if;

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'trainer_chat_sessions'
      and column_name = 'workout_id'
  ) then
    execute format('alter table public.trainer_chat_sessions add column workout_id %s', workouts_id_type);
  end if;

  if not exists (
    select 1
    from information_schema.table_constraints tc
    where tc.table_schema = 'public'
      and tc.table_name = 'trainer_chat_sessions'
      and tc.constraint_type = 'FOREIGN KEY'
      and tc.constraint_name = 'trainer_chat_sessions_workout_id_fkey'
  ) then
    execute 'alter table public.trainer_chat_sessions add constraint trainer_chat_sessions_workout_id_fkey foreign key (workout_id) references public.workouts(id) on delete cascade';
  end if;

  create index if not exists idx_trainer_chat_sessions_workout_id on public.trainer_chat_sessions(workout_id);

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'trainer_chat_sessions'
      and column_name = 'original_workout_details'
  ) then
    execute 'alter table public.trainer_chat_sessions add column original_workout_details jsonb';
  end if;

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'trainer_chat_sessions'
      and column_name = 'updated_workout_details'
  ) then
    execute 'alter table public.trainer_chat_sessions add column updated_workout_details jsonb';
  end if;

  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'trainer_chat_sessions'
      and column_name = 'updated_at'
  ) then
    execute 'alter table public.trainer_chat_sessions add column updated_at timestamp with time zone default timezone(''utc''::text, now()) not null';
  end if;
end $$;


