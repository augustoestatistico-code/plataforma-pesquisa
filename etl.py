import requests
import pandas as pd
import json
from requests.auth import HTTPBasicAuth
from sqlalchemy import create_engine, text
import os

# ===== CONFIG =====

ODK_URL="https://app.ar7pesquisas.com.br"
ODK_USER="augusto.estatistico@gmail.com"
ODK_PASS="@Mat050dois"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL não definida")

engine = create_engine(DATABASE_URL)

# ===== BUSCAR PESQUISA =====
df_pesquisa = pd.read_sql("SELECT * FROM pesquisas LIMIT 1", engine)

if df_pesquisa.empty:
    raise ValueError("❌ Tabela pesquisas vazia")

pesquisa = df_pesquisa.iloc[0]

print("USANDO PESQUISA:", pesquisa['nome'])

# ===== BUSCAR DADOS ODK =====
url = f"{ODK_URL}/v1/projects/{pesquisa['projeto_odk']}/forms/{pesquisa['form_id']}.svc/Submissions"

r = requests.get(url, auth=HTTPBasicAuth(ODK_USER, ODK_PASS))

if r.status_code != 200:
    raise ValueError(f"Erro ODK: {r.status_code}")

data = r.json().get('value', [])

df = pd.DataFrame(data)

print("TOTAL:", len(df))

if df.empty:
    print("⚠️ Nenhum dado retornado")
    exit()

# ===== INSERIR NO BANCO =====
with engine.begin() as conn:

    for _, row in df.iterrows():

        dados = row.where(pd.notnull(row), None).to_dict()

        sexo = dados.get("SEXO")
        idade = dados.get("IDADE")
        localidade = dados.get("LOCALIDADE")

        try:
            conn.execute(text("""
                INSERT INTO entrevistas (
                    submission_id,
                    pesquisa_id,
                    sexo,
                    idade,
                    localidade,
                    dados
                )
                VALUES (
                    :submission_id,
                    :pesquisa_id,
                    :sexo,
                    :idade,
                    :localidade,
                    :dados
                )
                ON CONFLICT (submission_id) DO NOTHING
            """), {
                "submission_id": dados.get("__id"),
                "pesquisa_id": int(pesquisa['id']),
                "sexo": sexo,
                "idade": idade,
                "localidade": localidade,
                "dados": json.dumps(dados, ensure_ascii=False)
            })

        except Exception as e:
            print("ERRO AO INSERIR:", e)

print("✅ ETL FINALIZADO COM SUCESSO")