"""Throw-away read-only schema/settings check for REPORT_4. Not imported by the app."""
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
env = (ROOT / "backend" / ".env").read_text(encoding="utf-8")
url = next(l.split("=", 1)[1].strip() for l in env.splitlines() if l.startswith("DATABASE_URL="))
rest = url[len("postgresql://") :]
creds, hd = rest.split("@", 1)
u, p = creds.split(":", 1)
hp, db = hd.split("/", 1)
h, port = hp.split(":")

c = psycopg2.connect(host=h, port=int(port), dbname=db, user=u, password=p)
c.set_session(readonly=True)
cur = c.cursor()

print("=== monitoring_observations + sessions columns ===")
cur.execute(
    """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name IN ('monitoring_observations','sessions')
    ORDER BY table_name, ordinal_position
    """
)
for r in cur.fetchall():
    print(r)

print("=== system_settings cooldown/intervention ===")
cur.execute(
    """
    SELECT key, value FROM system_settings
    WHERE key LIKE '%cooldown%' OR key LIKE '%intervention%' OR key LIKE '%tier%'
    ORDER BY key
    """
)
for r in cur.fetchall():
    print(r)

print("=== session 94 ===")
cur.execute(
    "SELECT id, student_id, module_content_id, started_at, ended_at FROM sessions WHERE id=94"
)
print(cur.fetchone())

print("=== subject via module_content → modules ===")
cur.execute(
    """
    SELECT mc.id AS content_id, m.id AS module_id, m.subject_id, s.title
    FROM module_contents mc
    JOIN modules m ON m.id = mc.module_id
    JOIN subjects s ON s.id = m.subject_id
    WHERE mc.id = (SELECT module_content_id FROM sessions WHERE id=94)
    """
)
print(cur.fetchone())

print("=== intervention_configs for that subject ===")
cur.execute(
    """
    SELECT column_name FROM information_schema.columns
    WHERE table_schema='public' AND table_name='intervention_configs'
    ORDER BY ordinal_position
    """
)
cols = [r[0] for r in cur.fetchall()]
print("cols:", cols)
if cols:
    cur.execute(
        """
        SELECT ic.id, ic.subject_id, ic.tier1_enabled, ic.tier2_enabled,
               ic.tier3_enabled, ic.tier4_enabled
        FROM intervention_configs ic
        WHERE ic.subject_id = (
            SELECT m.subject_id
            FROM module_contents mc
            JOIN modules m ON m.id = mc.module_id
            JOIN sessions sess ON sess.module_content_id = mc.id
            WHERE sess.id=94
        )
        """
    )
    rows = cur.fetchall()
    print("rows:", rows if rows else "(none — defaults [1,2,3,4] apply)")


print("=== DATABASE_URL redacted ===")
print(f"postgresql://{u}:***@{h}:{port}/{db}")
c.close()
