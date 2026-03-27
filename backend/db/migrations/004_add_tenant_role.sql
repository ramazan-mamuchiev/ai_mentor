-- Migration 004: Add role column to tenants for RBAC (admin panel)

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
