-- 011: Промокоды + переход на CloudPayments
-- Таблица промокодов

CREATE TABLE IF NOT EXISTS promo_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text UNIQUE NOT NULL,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamptz DEFAULT now()
);

-- Таблица событий по промокодам (воронка: start -> trial -> subscription)

CREATE TABLE IF NOT EXISTS promo_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id uuid NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('start', 'trial', 'subscription')),
    created_at timestamptz DEFAULT now(),
    UNIQUE(promo_code_id, user_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_promo_events_promo_code_id ON promo_events(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_events_user_id ON promo_events(user_id);

-- Новые колонки в users для промокодов и CloudPayments

ALTER TABLE users ADD COLUMN IF NOT EXISTS promo_code_id uuid REFERENCES promo_codes(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS cp_subscription_id text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS cp_token text;
