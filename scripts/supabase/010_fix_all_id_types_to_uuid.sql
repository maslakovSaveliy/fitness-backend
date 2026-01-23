-- Исправление типа id во ВСЕХ таблицах с text на uuid
-- ВАЖНО: Эта миграция удалит все существующие данные!
-- Применять вручную в Supabase SQL Editor

-- ========================================
-- ШАГ 1: Удалить все foreign key constraints
-- ========================================

-- Constraints для users
ALTER TABLE IF EXISTS trainer_chat_sessions DROP CONSTRAINT IF EXISTS trainer_chat_sessions_user_id_fkey;
ALTER TABLE IF EXISTS workouts DROP CONSTRAINT IF EXISTS workouts_user_id_fkey;
ALTER TABLE IF EXISTS meals DROP CONSTRAINT IF EXISTS meals_user_id_fkey;
ALTER TABLE IF EXISTS daily_nutrition_stats DROP CONSTRAINT IF EXISTS daily_nutrition_stats_user_id_fkey;
ALTER TABLE IF EXISTS nutrition_plans DROP CONSTRAINT IF EXISTS nutrition_plans_user_id_fkey;
ALTER TABLE IF EXISTS workout_drafts DROP CONSTRAINT IF EXISTS workout_drafts_user_id_fkey;
ALTER TABLE IF EXISTS user_reminders DROP CONSTRAINT IF EXISTS user_reminders_user_id_fkey;
ALTER TABLE IF EXISTS feedback DROP CONSTRAINT IF EXISTS feedback_user_id_fkey;

-- Constraints для других таблиц
ALTER TABLE IF EXISTS trainer_chat_messages DROP CONSTRAINT IF EXISTS trainer_chat_messages_session_id_fkey;
ALTER TABLE IF EXISTS nutrition_plan_menus DROP CONSTRAINT IF EXISTS nutrition_plan_menus_plan_id_fkey;
ALTER TABLE IF EXISTS trainer_chat_sessions DROP CONSTRAINT IF EXISTS trainer_chat_sessions_workout_id_fkey;

-- ========================================
-- ШАГ 2: Очистить все таблицы (удалить данные)
-- ========================================

TRUNCATE TABLE public.trainer_chat_messages CASCADE;
TRUNCATE TABLE public.trainer_chat_sessions CASCADE;
TRUNCATE TABLE public.nutrition_plan_menus CASCADE;
TRUNCATE TABLE public.nutrition_plans CASCADE;
TRUNCATE TABLE public.daily_nutrition_stats CASCADE;
TRUNCATE TABLE public.meals CASCADE;
TRUNCATE TABLE public.workouts CASCADE;
TRUNCATE TABLE public.workout_drafts CASCADE;
TRUNCATE TABLE public.user_reminders CASCADE;
TRUNCATE TABLE public.broadcasts CASCADE;
TRUNCATE TABLE public.feedback CASCADE;
TRUNCATE TABLE public.users CASCADE;

-- ========================================
-- ШАГ 3: Изменить тип id на uuid во всех таблицах
-- ========================================

-- users
ALTER TABLE public.users 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- workouts
ALTER TABLE public.workouts 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.workouts 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- meals
ALTER TABLE public.meals 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.meals 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- daily_nutrition_stats
ALTER TABLE public.daily_nutrition_stats 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.daily_nutrition_stats 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- nutrition_plans
ALTER TABLE public.nutrition_plans 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.nutrition_plans 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- nutrition_plan_menus
ALTER TABLE public.nutrition_plan_menus 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.nutrition_plan_menus 
ALTER COLUMN plan_id TYPE uuid USING gen_random_uuid();

-- trainer_chat_sessions
ALTER TABLE public.trainer_chat_sessions 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.trainer_chat_sessions 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

ALTER TABLE IF EXISTS public.trainer_chat_sessions 
ALTER COLUMN workout_id TYPE uuid USING NULL;

-- trainer_chat_messages
ALTER TABLE public.trainer_chat_messages 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.trainer_chat_messages 
ALTER COLUMN session_id TYPE uuid USING gen_random_uuid();

-- workout_drafts (если существует)
DO $$ 
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workout_drafts') THEN
    ALTER TABLE public.workout_drafts 
    ALTER COLUMN id DROP DEFAULT,
    ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

    ALTER TABLE public.workout_drafts 
    ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();
  END IF;
END $$;

-- user_reminders
ALTER TABLE public.user_reminders 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.user_reminders 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- broadcasts
ALTER TABLE public.broadcasts 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- feedback
ALTER TABLE public.feedback 
ALTER COLUMN id DROP DEFAULT,
ALTER COLUMN id TYPE uuid USING gen_random_uuid(),
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE public.feedback 
ALTER COLUMN user_id TYPE uuid USING gen_random_uuid();

-- ========================================
-- ШАГ 4: Восстановить foreign key constraints
-- ========================================

-- Constraints для users
ALTER TABLE public.trainer_chat_sessions 
ADD CONSTRAINT trainer_chat_sessions_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.workouts 
ADD CONSTRAINT workouts_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.meals 
ADD CONSTRAINT meals_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.daily_nutrition_stats 
ADD CONSTRAINT daily_nutrition_stats_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.nutrition_plans 
ADD CONSTRAINT nutrition_plans_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.user_reminders 
ADD CONSTRAINT user_reminders_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.feedback 
ADD CONSTRAINT feedback_user_id_fkey 
FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- Constraint для nutrition_plan_menus
ALTER TABLE public.nutrition_plan_menus 
ADD CONSTRAINT nutrition_plan_menus_plan_id_fkey 
FOREIGN KEY (plan_id) REFERENCES public.nutrition_plans(id) ON DELETE CASCADE;

-- Constraint для trainer_chat_messages
ALTER TABLE public.trainer_chat_messages 
ADD CONSTRAINT trainer_chat_messages_session_id_fkey 
FOREIGN KEY (session_id) REFERENCES public.trainer_chat_sessions(id) ON DELETE CASCADE;

-- Constraint для trainer_chat_sessions -> workouts (nullable)
ALTER TABLE public.trainer_chat_sessions 
ADD CONSTRAINT trainer_chat_sessions_workout_id_fkey 
FOREIGN KEY (workout_id) REFERENCES public.workouts(id) ON DELETE SET NULL;

-- Constraint для workout_drafts (если существует)
DO $$ 
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workout_drafts') THEN
    ALTER TABLE public.workout_drafts 
    ADD CONSTRAINT workout_drafts_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
  END IF;
END $$;

-- ========================================
-- Готово!
-- ========================================
