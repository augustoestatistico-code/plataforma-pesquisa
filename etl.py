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
    urls_visitadas = set()
    pagina_num = 0
    MAX_PAGINAS = 500

    while url:

        # Evita loop infinito se o ODK repetir o mesmo nextLink
        if url in urls_visitadas:
            print("ERRO: ODK repetiu uma URL. Interrompendo paginação.")
            print("URL repetida:", url)
            break

        urls_visitadas.add(url)

        pagina_num += 1

        if pagina_num > MAX_PAGINAS:
            print(
                f"ERRO: limite de {MAX_PAGINAS} páginas atingido. "
                "Interrompendo paginação."
            )
            break

        print(f"BUSCANDO PAGINA {pagina_num}: {url}")

        try:

            r = requests.get(
                url,
                auth=HTTPBasicAuth(ODK_USER, ODK_PASS),
                timeout=(15, 60)
            )

            r.raise_for_status()

        except requests.exceptions.Timeout:
            print(
                f"ERRO: timeout no ODK na página {pagina_num}"
            )
            raise

        except requests.exceptions.RequestException as e:
            print(
                f"ERRO DE CONEXAO ODK na página {pagina_num}: {e}"
            )
            raise

        try:
            js = r.json()

        except ValueError:
            print(
                f"ERRO: resposta inválida do ODK na página {pagina_num}"
            )
            raise

        pagina = js.get("value", [])

        todos.extend(pagina)

        print(
            f"PAGINA {pagina_num}: "
            f"{len(pagina)} registros | "
            f"TOTAL ACUMULADO: {len(todos)}"
        )

        proxima_url = js.get("@odata.nextLink")

        if not proxima_url:
            break

        url = proxima_url

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
      AND COALESCE(atualizar_auto, false) = true
    ORDER BY id
""", engine)

if PESQUISA_ID:
    pesquisas = pesquisas[
        pesquisas["id"] == int(PESQUISA_ID)
    ]

print("\nPESQUISAS ENCONTRADAS:")
print(
    pesquisas[
        ["id", "nome"]
    ]
)

# ======================
# LOOP
# ======================

for _, pesquisa in pesquisas.iterrows():

    try:

        print("\n=================")
        print("PROCESSANDO:", pesquisa["nome"])

        # =========================
        # VALIDAR DADOS ODK
        # =========================
        if pd.isna(pesquisa["projeto_odk"]) or pd.isna(pesquisa["form_id"]):
            print(
                "IGNORANDO PESQUISA COM DADOS ODK INVÁLIDOS:",
                pesquisa["nome"]
            )
            continue

        # =========================
        # CONVERTER PROJETO ODK
        # Ex.: 4.0 -> 4
        # =========================
        projeto_odk = int(float(pesquisa["projeto_odk"]))
        form_id = str(pesquisa["form_id"]).strip()

        if not form_id or form_id.lower() == "nan":
            print(
                "IGNORANDO PESQUISA SEM FORM_ID:",
                pesquisa["nome"]
            )
            continue

        print("Projeto ODK original :", pesquisa["projeto_odk"])
        print("Projeto convertido   :", projeto_odk)
        print("Form ID              :", form_id)

        # =========================
        # MONTAR URL ODK
        # =========================
        url = (
            f"{ODK_URL}/v1/projects/{projeto_odk}"
            f"/forms/{form_id}.svc/Submissions"
        )

        print("BUSCANDO:", url)

        data = buscar_todas_submissoes(url)

        print("TOTAL ODK:", len(data))
        

        if len(data) == 0:
            continue

        df = pd.DataFrame(data)

        # ==========================================
        # FILTRAR SOMENTE ENTREVISTAS NOVAS
        # ==========================================

        if "__id" not in df.columns:
            print("ERRO: campo __id não encontrado nas submissões ODK")
            continue

        total_odk = len(df)

        with engine.connect() as conn:
            existentes = conn.execute(
                text("""
                    SELECT submission_id
                    FROM entrevistas
                    WHERE pesquisa_id = :pesquisa_id
                """),
                {
                    "pesquisa_id": int(pesquisa["id"])
                }
            ).scalars().all()

        ids_existentes = set(existentes)

        df = df[
            ~df["__id"].isin(ids_existentes)
        ].copy()

        print("JÁ EXISTENTES:", total_odk - len(df))
        print("NOVAS:", len(df))

        if df.empty:
            print(
                "SEM NOVAS ENTREVISTAS:",
                pesquisa["nome"]
            )
            continue

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
