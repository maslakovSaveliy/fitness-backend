-- Добавление поля onboarding_completed для отслеживания прохождения онбординга
-- Это поле нужно чтобы отличать новых пользователей (которым нужен онбординг)
-- от существующих (которым онбординг уже не нужен)

ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT false;

-- Для существующих пользователей с заполненным профилем ставим onboarding_completed = true
-- так как они уже прошли онбординг в старой версии
UPDATE users 
SET onboarding_completed = true 
WHERE has_profile = true;

-- Также для пользователей которые имеют заполненные поля профиля
UPDATE users 
SET onboarding_completed = true 
WHERE goal IS NOT NULL 
  AND level IS NOT NULL 
  AND location IS NOT NULL;
