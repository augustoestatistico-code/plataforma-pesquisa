import requests
import pandas as pd
import json
from requests.auth import HTTPBasicAuth
from sqlalchemy import create_engine, text
import os

# ======================
# CONFIG
# ======================

ODK_URL = "https://app.ar7pesquisas.com.br"
ODK_USER = "augusto.estatistico@gmail.com"
ODK_PASS = "@Mat050dois"

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

# ======================
# BUSCAR TODAS PESQUISAS
# ======================

pesquisas = pd.read_sql("""
SELECT
    id,
    nome,
    projeto_odk,
    form_id
FROM pesquisas
ORDER BY id
""", engine)

print("PESQUISAS ENCONTRADAS:")
print(pesquisas[["id","nome"]])

# ======================
# LOOP EM TODAS
# ======================

for _, pesquisa in pesquisas.iterrows():

    try:

        print(f"\nPROCESSANDO: {pesquisa['nome']}")

        url = (
            f"{ODK_URL}/v1/projects/"
            f"{pesquisa['projeto_odk']}"
            f"/forms/"
            f"{pesquisa['form_id']}.svc/Submissions"
        )

        r = requests.get(
            url,
            auth=HTTPBasicAuth(
                ODK_USER,
                ODK_PASS
            )
        )

        if r.status_code != 200:

            print(
                f"ERRO API {r.status_code}"
            )

            continue

        data = r.json().get(
            "value",
            []
        )

        df = pd.DataFrame(data)

        print(
            "TOTAL:",
            len(df)
        )

        if df.empty:
            continue

        with engine.begin() as conn:

            for _, row in df.iterrows():

                dados = (
                    row.where(
                        pd.notnull(row),
                        None
                    )
                    .to_dict()
                )

                sexo = dados.get("SEXO")
                idade = dados.get("IDADE")
                localidade = dados.get("LOCALIDADE")
                entrevistador = dados.get("ENTREVISTADOR")

                conn.execute(
                    text("""
                    INSERT INTO entrevistas(
                        submission_id,
                        pesquisa_id,
                        sexo,
                        idade,
                        localidade,
                        entrevistador,
                        dados
                    )
                    VALUES(
                        :submission_id,
                        :pesquisa_id,
                        :sexo,
                        :idade,
                        :localidade,
                        :entrevistador,
                        :dados
                    )
                    ON CONFLICT
                    (submission_id)
                    DO NOTHING
                    """),
                    {
                        "submission_id":
                        dados.get("__id"),

                        "pesquisa_id":
                        int(
                            pesquisa["id"]
                        ),

                        "sexo":
                        sexo,

                        "idade":
                        idade,

                        "localidade":
                        localidade,

                        "entrevistador":
                        entrevistador,

                        "dados":
                        json.dumps(
                            dados,
                            ensure_ascii=False
                        )
                    }
                )

        print(
            f"OK: {pesquisa['nome']}"
        )

    except Exception as e:

        print(
            f"ERRO {pesquisa['nome']}:",
            e
        )

print("\nETL FINALIZADO")