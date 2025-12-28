-- nutrition_plan_menus
-- Apply manually in Supabase SQL editor.

create table if not exists nutrition_plan_menus (
  id uuid default gen_random_uuid() primary key,
  plan_id uuid references nutrition_plans(id) on delete cascade,
  date date not null,
  menu_text text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  unique(plan_id, date)
);

create index if not exists idx_nutrition_plan_menus_plan_id
  on nutrition_plan_menus(plan_id);


