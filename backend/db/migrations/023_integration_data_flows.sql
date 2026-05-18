-- Add integration_data_flows column to api_lifecycles
ALTER TABLE api_lifecycles
    ADD COLUMN IF NOT EXISTS integration_data_flows jsonb NOT NULL DEFAULT '{}';
