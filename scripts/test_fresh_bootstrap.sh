#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_id="${RANDOM}-$$"
db_container="ideas-hub-fresh-bootstrap-db-${run_id}"
network_name="ideas-hub-fresh-bootstrap-net-${run_id}"
backend_image="ideas-hub-fresh-bootstrap-backend:${run_id}"
postgres_user="ideas_hub_test"
postgres_password="fresh-bootstrap-test"
postgres_db="ideas_hub_test"

cleanup() {
    docker rm -f "${db_container}" >/dev/null 2>&1 || true
    docker network rm "${network_name}" >/dev/null 2>&1 || true
    docker image rm "${backend_image}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "${network_name}" >/dev/null
docker run --detach \
    --name "${db_container}" \
    --network "${network_name}" \
    --tmpfs /var/lib/postgresql/data:rw \
    --env "POSTGRES_USER=${postgres_user}" \
    --env "POSTGRES_PASSWORD=${postgres_password}" \
    --env "POSTGRES_DB=${postgres_db}" \
    --volume "${repo_dir}/db/init/001_init.sql:/docker-entrypoint-initdb.d/001_init.sql:ro" \
    pgvector/pgvector:pg16 >/dev/null

for _ in $(seq 1 60); do
    if docker exec "${db_container}" psql \
        --username "${postgres_user}" \
        --dbname "${postgres_db}" \
        --tuples-only \
        --no-align \
        --command "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_roteiros_atualizado';" \
        2>/dev/null | grep -qx '1'; then
        break
    fi
    sleep 1
done
docker exec "${db_container}" psql \
    --username "${postgres_user}" \
    --dbname "${postgres_db}" \
    --tuples-only \
    --no-align \
    --command "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_roteiros_atualizado';" \
    | grep -qx '1'

psql_scalar() {
    docker exec "${db_container}" psql \
        --username "${postgres_user}" \
        --dbname "${postgres_db}" \
        --tuples-only \
        --no-align \
        --command "$1"
}

baseline_column_count="$(psql_scalar "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'nichos' AND column_name = 'perfil_producao';")"
baseline_enum_count="$(psql_scalar "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'origem_ideia' AND e.enumlabel = 'notas_gameplay';")"
test "${baseline_column_count}" = "0"
test "${baseline_enum_count}" = "0"

docker build --quiet --tag "${backend_image}" "${repo_dir}/backend" >/dev/null
database_url="postgresql+asyncpg://${postgres_user}:${postgres_password}@${db_container}:5432/${postgres_db}"
docker run --rm \
    --network "${network_name}" \
    --env "DATABASE_URL=${database_url}" \
    --env "PYTHONPATH=/app" \
    "${backend_image}" \
    alembic upgrade head

final_column="$(psql_scalar "SELECT count(*) || '|' || min(data_type) || '|' || min(character_maximum_length)::text || '|' || min(is_nullable) || '|' || min(column_default) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'nichos' AND column_name = 'perfil_producao';")"
final_enum_count="$(psql_scalar "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'origem_ideia' AND e.enumlabel = 'notas_gameplay';")"
database_revision="$(psql_scalar "SELECT version_num FROM alembic_version;")"
expected_revision="$(docker run --rm --env "PYTHONPATH=/app" "${backend_image}" alembic heads | awk 'NR == 1 {print $1}')"

test "${final_column}" = "1|character varying|50|NO|'faceless_general'::character varying"
test "${final_enum_count}" = "1"
test "${database_revision}" = "${expected_revision}"

echo "Fresh bootstrap regression passed."
echo "Baseline: perfil_producao=absent, notas_gameplay=absent"
echo "Head: perfil_producao=VARCHAR(50) NOT NULL DEFAULT faceless_general"
echo "Head: notas_gameplay=present, alembic_revision=${database_revision}"
