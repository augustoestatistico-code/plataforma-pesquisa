import requests
import pandas as pd
import json
from requests.auth import HTTPBasicAuth
from sqlalchemy import create_engine, text
import os
PESQUISA_ID = os.getenv("PESQUISA_ID")

# ======================
# CONFIG
# ======================

ODK_URL = "https://app.ar7pesquisas.com.br"
ODK_USER = "augusto.estatistico@gmail.com"
ODK_PASS = "@Mat050dois"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

print("DATABASE_URL =", repr(DATABASE_URL))

if not DATABASE_URL:
    raise ValueError("DATABASE_URL está vazia. Defina com: set DATABASE_URL=sua_url")

if not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg2://")):
    raise ValueError(f"DATABASE_URL inválida: {DATABASE_URL}")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "connect_timeout": 30,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
)

# ======================
# BUSCAR TODAS PÁGINAS ODK
# ======================
def buscar_todas_submissoes(url):

    todos = []

    while url:

        print("BUSCANDO:", url)

        r = requests.get(
            url,
            auth=HTTPBasicAuth(ODK_USER, ODK_PASS),
            timeout=(30, 180)
        )

        if r.status_code != 200:

            print(
                "ERRO API:",
                r.status_code
            )

            print(
                r.text[:500]
            )

            return []

        js = r.json()

        pagina = js.get(
            "value",
            []
        )

        todos.extend(
            pagina
        )

        url = js.get(
            "@odata.nextLink"
        )

    return todos

# ======================
# BUSCAR PESQUISAS
# ======================

pesquisas = pd.read_sql("""
    SELECT
        id,
        nome,
        projeto_odk,
        form_id,
        origem
    FROM pesquisas
    WHERE UPPER(COALESCE(origem, 'ODK')) = 'ODK'
      AND projeto_odk IS NOT NULL
      AND form_id IS NOT NULL
      AND TRIM(CAST(form_id AS TEXT)) <> ''
    ORDER BY id
""", engine)

if PESQUISA_ID:
    pesquisas = pesquisas[
        pesquisas["id"] == int(PESQUISA_ID)
    ]
    
print("\nPESQUISAS ENCONTRADAS:")
print(
    pesquisas[
        ["id","nome"]
    ]
)

# ======================
# LOOP
# ======================

for _, pesquisa in pesquisas.iterrows():

    try:

        print("\n=================")
        print("PROCESSANDO:", pesquisa["nome"])

        projeto_odk = int(str(pesquisa["projeto_odk"]).split(".")[0])
        form_id = str(pesquisa["form_id"]).strip()

        print("Projeto ODK original :", pesquisa["projeto_odk"])
        print("Projeto convertido   :", projeto_odk)
        print("Form ID              :", form_id)

        print("PROCESSANDO:", pesquisa["nome"])

        # 🔴 VALIDAÇÃO (COLOQUE ISSO AQUI)
        if pd.isna(pesquisa["projeto_odk"]) or pd.isna(pesquisa["form_id"]):
            print("IGNORANDO PESQUISA COM DADOS INVÁLIDOS:", pesquisa["nome"])
            continue

        # 🔵 CONVERSÃO SEGURA
        projeto_odk = int(str(pesquisa["projeto_odk"]).replace(".0", "").strip())
        form_id = str(pesquisa["form_id"]).strip()

        # 🟢 AGORA MONTA A URL
        url = (
            f"{ODK_URL}/v1/projects/{projeto_odk}"
            f"/forms/{form_id}.svc/Submissions"
        )

        print("BUSCANDO:", url)

        data = buscar_todas_submissoes(url)

        

        data = buscar_todas_submissoes(url)

        print("TOTAL ODK:", len(data))

        if len(data) == 0:
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

                localidade = (
                        dados.get("LOCALIDADE")
                        or dados.get("localidade")
                        or dados.get("bairros")
                        or dados.get("bairro")
                        or dados.get("BAIRRO")
                        or dados.get("ZONA")
                        or dados.get("zona")
                        or "Não informado"
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
                    (pesquisa_id, submission_id)
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
                            (pesquisa_id, submission_id, nome_arquivo)

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
