"""Correct trigger alias collision with PostgreSQL OLD/NEW transition records."""
from alembic import op
revision='20261028_epi07'
down_revision='20261028_epi06'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE OR REPLACE FUNCTION territory.check_universe_geometry() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM 1 FROM territory.universo WHERE id=NEW.universo_id FOR UPDATE;
      IF EXISTS(SELECT 1 FROM territory.miembro_universo m
        JOIN territory.radio_censal existing_radio ON existing_radio.id=m.radio_id
        JOIN territory.radio_censal incoming_radio ON incoming_radio.id=NEW.radio_id
        WHERE m.universo_id=NEW.universo_id
          AND existing_radio.version_geometria_id<>incoming_radio.version_geometria_id)
      THEN RAISE EXCEPTION 'universe_geometry_versions_mixed'; END IF;
      RETURN NEW;
    END $$;
    ''')

def downgrade():raise RuntimeError('Destructive downgrade disabled')
