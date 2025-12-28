-- Выравнивание схемы под продовую Supabase (по текущим скриншотам).
-- Применять вручную в Supabase SQL Editor.
-- Основной момент: workouts.details = jsonb (в проде уже так).

-- users
create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint,
  username text,
  first_name text,
  last_name text,
  is_active boolean default true,
  is_paid boolean default false,
  paid_until timestamp,
  created_at timestamp default now(),
  last_active_at timestamp,
  role text default 'user'::text,
  goal text,
  level text,
  health_issues text,
  workouts_per_week text,
  height text,
  weight text,
  age text,
  gender text,
  location text,
  workout_duration text,
  equipment text,
  workout_formats text,
  last_muscle_group text,
  is_pro boolean default false,
  supersets_enabled boolean default false,
  custom_split_frequency int4,
  trial_expired boolean default false
);

-- workouts
create table if not exists public.workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  date date,
  workout_type text,
  details jsonb,
  calories_burned int4,
  created_at timestamp default now(),
  rating int4,
  comment text
);

-- если в старой схеме details был text, приводим к jsonb (как JSON-строка)
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema='public'
      and table_name='workouts'
      and column_name='details'
      and data_type='text'
  ) then
    execute 'alter table public.workouts alter column details type jsonb using to_jsonb(details)';
  end if;
end $$;

-- meals
create table if not exists public.meals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  date date,
  photo_url text,
  calories int4,
  description text,
  created_at timestamp default now(),
  proteins numeric,
  fats numeric,
  carbs numeric
);

-- daily_nutrition_stats
create table if not exists public.daily_nutrition_stats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  date date,
  total_calories numeric default 0,
  total_proteins numeric default 0,
  total_fats numeric default 0,
  total_carbs numeric default 0,
  meals_count int4 default 0,
  created_at timestamp default timezone('utc'::text, now()),
  updated_at timestamp default timezone('utc'::text, now())
);

-- nutrition_plans
create table if not exists public.nutrition_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade,
  nutrition_goal text,
  dietary_restrictions text,
  meal_preferences text,
  cooking_time text,
  budget text,
  target_calories int4,
  target_proteins numeric,
  target_fats numeric,
  target_carbs numeric,
  is_active bool default true,
  created_at timestamp default now(),
  updated_at timestamp default now()
);


