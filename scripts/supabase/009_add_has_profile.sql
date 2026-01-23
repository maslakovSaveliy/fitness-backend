-- Добавление поля has_profile для контроля onboarding
-- Применять вручную в Supabase SQL Editor

-- Добавляем поле has_profile (по умолчанию false для новых пользователей)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS has_profile boolean DEFAULT false;

-- Обновляем существующих пользователей у которых заполнен goal (считаем что прошли onboarding)
UPDATE public.users 
SET has_profile = true 
WHERE goal IS NOT NULL;

-- Индекс для быстрого поиска пользователей без профиля
CREATE INDEX IF NOT EXISTS idx_users_has_profile ON public.users(has_profile);
