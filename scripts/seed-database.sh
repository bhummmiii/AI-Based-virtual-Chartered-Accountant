#!/bin/bash
# ============================================================
# Seed Database Script
# ============================================================

echo "Seeding database..."
psql -U ca_admin -d ca_assistant_db -f database/seed/seed_data.sql
echo "Done!"
