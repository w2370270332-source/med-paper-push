-- 文献推送系统数据库 Schema
-- 在 Supabase SQL Editor 中执行

-- 邀请码表
CREATE TABLE invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    created_by UUID REFERENCES auth.users(id),
    used_by UUID REFERENCES auth.users(id),
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 用户偏好表
CREATE TABLE user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) UNIQUE NOT NULL,
    -- 研究领域 (多选用 JSON 数组)
    research_areas JSONB DEFAULT '[]'::jsonb,
    -- 中科院分区筛选 (如 ["1","2"])
    cas_quartiles JSONB DEFAULT '["1","2","3","4"]'::jsonb,
    -- 影响因子最小值 (0 表示不筛选)
    min_impact_factor REAL DEFAULT 0,
    -- 推送频率: daily / weekly / weekdays
    push_frequency TEXT DEFAULT 'daily',
    -- 指定工作日 (仅 weekdays 模式有效，如 ["1","3","5"])
    push_days JSONB DEFAULT '[]'::jsonb,
    -- 是否启用推送
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 论文池表 (Actions 写入)
CREATE TABLE paper_pool (
    id BIGSERIAL PRIMARY KEY,
    pmid TEXT,
    title TEXT NOT NULL,
    title_cn TEXT,
    original_title TEXT,
    source TEXT,
    url TEXT,
    abstract TEXT,
    study_type TEXT,
    journal TEXT,
    impact_factor REAL,
    cas_quartile TEXT,
    background TEXT,
    methods TEXT,
    findings TEXT,
    significance TEXT,
    limitation TEXT,
    relevance TEXT,
    research_area TEXT,
    pub_date DATE,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

-- 推送历史表
CREATE TABLE push_history (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    paper_ids JSONB NOT NULL,
    paper_count INT NOT NULL,
    report_content TEXT,
    pushed_at TIMESTAMPTZ DEFAULT now()
);

-- 索引
CREATE INDEX idx_invite_codes_code ON invite_codes(code);
CREATE INDEX idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX idx_paper_pool_pub_date ON paper_pool(pub_date);
CREATE INDEX idx_paper_pool_research_area ON paper_pool USING gin(research_area);
CREATE INDEX idx_push_history_user_id ON push_history(user_id);
CREATE INDEX idx_push_history_pushed_at ON push_history(pushed_at);

-- RLS 策略
ALTER TABLE invite_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_pool ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_history ENABLE ROW LEVEL SECURITY;

-- 注册时检查邀请码并标记为已用 (trigger function)
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS trigger AS $$
DECLARE
    invite_code TEXT;
BEGIN
    invite_code := NEW.raw_user_meta_data ->> 'invite_code';

    IF invite_code IS NULL OR invite_code = '' THEN
        RAISE EXCEPTION '邀请码不能为空';
    END IF;

    UPDATE invite_codes
    SET used_by = NEW.id, used_at = now()
    WHERE code = invite_code
      AND used_by IS NULL;

    IF NOT FOUND THEN
        RAISE EXCEPTION '邀请码无效或已被使用';
    END IF;

    -- 创建默认偏好
    INSERT INTO user_preferences (user_id) VALUES (NEW.id);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 注册 trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- 管理员 RLS (通过 raw_app_meta_data 判断)
CREATE OR REPLACE FUNCTION is_admin()
RETURNS boolean AS $$
BEGIN
    RETURN coalesce(
        (SELECT raw_app_meta_data ->> 'role' = 'admin'
         FROM auth.users WHERE id = auth.uid()),
        false
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- paper_pool: 所有人可读
CREATE POLICY "Anyone can read papers" ON paper_pool
    FOR SELECT USING (true);

-- user_preferences: 用户读写自己的，管理员可读所有
CREATE POLICY "Users manage own preferences" ON user_preferences
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Admin reads all preferences" ON user_preferences
    FOR SELECT USING (is_admin());

-- push_history: 用户读自己的，管理员可读所有
CREATE POLICY "Users read own history" ON push_history
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Admin reads all history" ON push_history
    FOR SELECT USING (is_admin());

-- invite_codes: 管理员可读写
CREATE POLICY "Admin manages invites" ON invite_codes
    FOR ALL USING (is_admin())
    WITH CHECK (is_admin());

-- 公开读 (用于注册时查询)
CREATE POLICY "Anyone can read unused codes" ON invite_codes
    FOR SELECT USING (used_by IS NULL);
