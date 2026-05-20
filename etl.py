import requests
import pandas as pd
import psycopg2
import json
from requests.auth import HTTPBasicAuth
from sqlalchemy import create_engine
from config import *

engine = create_engine(
    "postgresql://postgres:123456@localhost:5432/plataforma_pesquisa"
)

conn = engine.raw_connection()
cur = conn.cursor()

pesquisas = pd.read_sql("SELECT * FROM pesquisas", engine)

for _, p in pesquisas.iterrows():

    projeto = p['projeto_odk']
    form_id = p['form_id']
    cliente_id = p['cliente_id']
    pesquisa_id = p['id']

    url = f"{ODK_URL}/v1/projects/{projeto}/forms/{form_id}.svc/Submissions"

    r = requests.get(
        url,
        auth=HTTPBasicAuth(ODK_USER, ODK_PASS)
    )

    data = r.json().get('value', [])

    df = pd.DataFrame(data)

    if df.empty:
        continue

    for _, row in df.iterrows():

        dados = row.where(pd.notnull(row), None).to_dict()

        cur.execute("""
        INSERT INTO entrevistas (
            submission_id,
            cliente_id,
            pesquisa_id,
            sexo,
            idade,
            localidade,
            dados
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (submission_id) DO NOTHING
        """, (
            row.get('__id'),
            cliente_id,
            pesquisa_id,
            row.get('SEXO'),
            row.get('IDADE'),
            row.get('LOCALIDADE'),
            json.dumps(dados, ensure_ascii=False)
        ))

conn.commit()

print("✅ ETL CONCLUÍDO")