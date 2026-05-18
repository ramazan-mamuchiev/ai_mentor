-- Add lifecycle.run permission to admin and publisher roles
UPDATE roles
SET permissions = jsonb_set(permissions, '{features,lifecycle.run}', 'true'::jsonb)
WHERE slug IN ('admin', 'publisher');
