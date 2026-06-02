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
# BUSCAR TODAS PÁGINAS ODK
# ======================

def buscar_todas_submissoes(url):

    todos=[]

    while url:

        print("BUSCANDO:",url)

        r=requests.get(
            url,
            auth=HTTPBasicAuth(
                ODK_USER,
                ODK_PASS
            )
        )

        if r.status_code!=200:

            print(
                "ERRO API:",
                r.status_code
            )

            print(
                r.text[:500]
            )

            return []

        js=r.json()

        pagina=js.get(
            "value",
            []
        )

        todos.extend(
            pagina
        )

        url=js.get(
            "@odata.nextLink"
        )

    return todos


# ======================
# BUSCAR PESQUISAS
# ======================

pesquisas=pd.read_sql("""

SELECT
    id,
    nome,
    projeto_odk,
    form_id

FROM pesquisas

ORDER BY id

""",engine)

print("\nPESQUISAS ENCONTRADAS:")
print(
    pesquisas[
        ["id","nome"]
    ]
)

# ======================
# LOOP
# ======================

for _,pesquisa in pesquisas.iterrows():

    try:

        print(
            "\n================="
        )

        print(
            "PROCESSANDO:",
            pesquisa["nome"]
        )

        url=(

            f"{ODK_URL}/v1/projects/"
            f"{pesquisa['projeto_odk']}"
            f"/forms/"
            f"{pesquisa['form_id']}"
            ".svc/Submissions"

        )

        data=buscar_todas_submissoes(
            url
        )

        print(
            "TOTAL ODK:",
            len(data)
        )

        if len(data)==0:

            continue

        df=pd.DataFrame(data)

        with engine.begin() as conn:

            for _,row in df.iterrows():

                dados=(

                    row.where(
                        pd.notnull(row),
                        None
                    )

                    .to_dict()

                )

                sexo=dados.get(
                    "SEXO"
                )

                idade=dados.get(
                    "IDADE"
                )

                localidade=dados.get(
                    "LOCALIDADE"
                )

                entrevistador=dados.get(
                    "ENTREVISTADOR"
                )
                audio_entrevista = dados.get(
                    "audio_entrevista"
                )

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

                        dados.get(
                            "__id"
                        ),

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

                if audio_entrevista:

                    conn.execute(

                        text("""

                            INSERT INTO audios_entrevistas(

                                pesquisa_id,
                                submission_id,
                                entrevistador,
                                localidade,
                                data_entrevista,
                                nome_arquivo

                            )

                            VALUES(

                                :pesquisa_id,
                                :submission_id,
                                :entrevistador,
                                :localidade,
                                :data_entrevista,
                                :nome_arquivo

                            )

                            ON CONFLICT
                            (submission_id, nome_arquivo)

                            DO NOTHING

                        """),

                        {

                            "pesquisa_id":
                            int(pesquisa["id"]),
                            "submission_id":
                            dados.get("__id"),

                            "entrevistador":
                            entrevistador,
    
                            "localidade":
                            localidade,

                            "data_entrevista":
                            dados.get("data_entrevista"),

                            "nome_arquivo":
                            audio_entrevista

                        }

                    )   
                

        print(
            "OK:",
            pesquisa["nome"]
        )

    except Exception as e:

        print(
            "ERRO:",
            pesquisa["nome"]
        )

        print(
            str(e)
        )

print("\nETL FINALIZADO E ATUALIZADO")
