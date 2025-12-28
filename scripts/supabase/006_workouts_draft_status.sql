-- Добавляем поддержку draft/completed для тренировок.
-- Применять вручную в Supabase SQL Editor.

do $$
begin
  -- status: draft | completed
  if not exists (
    select 1
    from information_schema.columns
    where table_schema='public'
      and table_name='workouts'
      and column_name='status'
  ) then
    execute 'alter table public.workouts add column status text';
  end if;

  execute 'alter table public.workouts alter column status set default ''completed''';

  -- backfill для существующих записей
  execute 'update public.workouts set status = ''completed'' where status is null';

  -- generation_context: запоминаем входные данные генерации (мышцы, wellbeing_reason и т.п.)
  if not exists (
    select 1
    from information_schema.columns
    where table_schema='public'
      and table_name='workouts'
      and column_name='generation_context'
  ) then
    execute 'alter table public.workouts add column generation_context jsonb';
  end if;

  -- updated_at (опционально, но удобно для TTL/отладки)
  if not exists (
    select 1
    from information_schema.columns
    where table_schema='public'
      and table_name='workouts'
      and column_name='updated_at'
  ) then
    execute 'alter table public.workouts add column updated_at timestamp default now()';
  end if;
exception
  when others then
    -- если что-то пошло не так, хотим видеть ошибку в SQL Editor
    raise;
end $$;


