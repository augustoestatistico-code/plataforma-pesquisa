import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURAÇÃO
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL não encontrada. "
        "Configure a variável de ambiente antes de executar."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 30},
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def texto_limpo(valor):
    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    return texto


def normalizar_coluna(nome):
    nome = str(nome).strip()

    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ascii", "ignore").decode("utf-8")
    nome = nome.lower()

    nome = re.sub(r"[^a-z0-9]+", "_", nome)
    nome = re.sub(r"_+", "_", nome)
    nome = nome.strip("_")

    return nome or "coluna_sem_nome"


def criar_submission_id(pesquisa_id, numero_linha, dados):
    conteudo = json.dumps(
        dados,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    chave = f"{pesquisa_id}|{numero_linha}|{conteudo}"
    hash_id = hashlib.sha256(chave.encode("utf-8")).hexdigest()

    return f"excel:{hash_id}"


def localizar_coluna(colunas, possibilidades):
    mapa = {
        normalizar_coluna(coluna): coluna
        for coluna in colunas
    }

    for possibilidade in possibilidades:
        chave = normalizar_coluna(possibilidade)

        if chave in mapa:
            return mapa[chave]

    return None


def converter_valor_json(valor):
    if pd.isna(valor):
        return None

    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()

    if hasattr(valor, "item"):
        try:
            return valor.item()
        except Exception:
            pass

    return valor


def nome_unico(nome, nomes_existentes):
    nome_base = nome
    contador = 2

    while nome in nomes_existentes:
        nome = f"{nome_base}_{contador}"
        contador += 1

    return nome


def preparar_dataframe(caminho_arquivo, nome_aba=None):
    caminho = Path(caminho_arquivo)

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    extensao = caminho.suffix.lower()

    if extensao == ".csv":
        tentativas = [
            {"encoding": "utf-8-sig", "sep": None},
            {"encoding": "latin1", "sep": None},
            {"encoding": "cp1252", "sep": None},
        ]

        ultimo_erro = None

        for tentativa in tentativas:
            try:
                return pd.read_csv(
                    caminho,
                    encoding=tentativa["encoding"],
                    sep=tentativa["sep"],
                    engine="python",
                )
            except Exception as erro:
                ultimo_erro = erro

        raise ValueError(
            f"Não foi possível ler o CSV: {ultimo_erro}"
        )

    if extensao in [".xlsx", ".xlsm", ".xls"]:
        return pd.read_excel(
            caminho,
            sheet_name=nome_aba if nome_aba else 0,
        )

    raise ValueError(
        "Formato não suportado. Use XLSX, XLS, XLSM ou CSV."
    )


def preparar_nomes_colunas(df):
    colunas_novas = []
    nomes_usados = set()
    de_para = {}

    for coluna_original in df.columns:
        nome = normalizar_coluna(coluna_original)
        nome = nome_unico(nome, nomes_usados)

        nomes_usados.add(nome)
        colunas_novas.append(nome)
        de_para[nome] = str(coluna_original).strip()

    df = df.copy()
    df.columns = colunas_novas

    return df, de_para


# ============================================================
# PESQUISA
# ============================================================

def criar_ou_localizar_pesquisa(
    nome_pesquisa,
    cliente_id,
    nome_arquivo,
    pesquisa_id=None,
):
    with engine.begin() as conn:

        if pesquisa_id:
            pesquisa = conn.execute(
                text("""
                    SELECT id, nome, cliente_id
                    FROM pesquisas
                    WHERE id = :pesquisa_id
                """),
                {"pesquisa_id": pesquisa_id},
            ).fetchone()

            if not pesquisa:
                raise ValueError(
                    f"Pesquisa ID {pesquisa_id} não encontrada."
                )

            if int(pesquisa.cliente_id) != int(cliente_id):
                raise ValueError(
                    "A pesquisa informada pertence a outro cliente."
                )

            conn.execute(
                text("""
                    UPDATE pesquisas
                    SET
                        origem = 'EXCEL',
                        arquivo_origem = :arquivo,
                        data_importacao = NOW()
                    WHERE id = :pesquisa_id
                """),
                {
                    "arquivo": nome_arquivo,
                    "pesquisa_id": pesquisa_id,
                },
            )

            return int(pesquisa_id)

        resultado = conn.execute(
            text("""
                INSERT INTO pesquisas (
                    nome,
                    cliente_id,
                    projeto_odk,
                    form_id,
                    origem,
                    arquivo_origem,
                    data_importacao
                )
                VALUES (
                    :nome,
                    :cliente_id,
                    NULL,
                    NULL,
                    'EXCEL',
                    :arquivo,
                    NOW()
                )
                RETURNING id
            """),
            {
                "nome": nome_pesquisa,
                "cliente_id": cliente_id,
                "arquivo": nome_arquivo,
            },
        ).fetchone()

        return int(resultado.id)


# ============================================================
# IMPORTAÇÃO DAS PERGUNTAS
# ============================================================

def importar_perguntas(pesquisa_id, de_para_colunas):
    campos_tecnicos = {
        "id",
        "submission_id",
        "pesquisa_id",
        "start",
        "end",
        "deviceid",
        "instanceid",
        "uuid",
        "meta_instanceid",
        "data_entrevista",
        "data",
        "hora",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "gps",
        "acc_inicio",
        "alt_inicio",
        "lat_inicio",
        "lon_inicio",
        "acc_final",
        "alt_final",
        "lat_final",
        "lon_final",
    }

    inseridas = 0

    with engine.begin() as conn:
        for ordem, (nome, label) in enumerate(
            de_para_colunas.items(),
            start=1,
        ):
            if nome in campos_tecnicos:
                continue

            existe = conn.execute(
                text("""
                    SELECT id
                    FROM perguntas_pesquisa
                    WHERE pesquisa_id = :pesquisa_id
                      AND UPPER(name) = UPPER(:name)
                    LIMIT 1
                """),
                {
                    "pesquisa_id": pesquisa_id,
                    "name": nome,
                },
            ).fetchone()

            if existe:
                conn.execute(
                    text("""
                        UPDATE perguntas_pesquisa
                        SET label = :label
                        WHERE id = :id
                    """),
                    {
                        "label": label,
                        "id": existe.id,
                    },
                )
                continue

            conn.execute(
                text("""
                    INSERT INTO perguntas_pesquisa (
                        pesquisa_id,
                        name,
                        label,
                        exibir_dashboard
                    )
                    VALUES (
                        :pesquisa_id,
                        :name,
                        :label,
                        TRUE
                    )
                """),
                {
                    "pesquisa_id": pesquisa_id,
                    "name": nome,
                    "label": label,
                },
            )

            inseridas += 1

    return inseridas


# ============================================================
# IMPORTAÇÃO DAS ENTREVISTAS
# ============================================================

def importar_entrevistas(df, pesquisa_id):
    coluna_sexo = localizar_coluna(
        df.columns,
        [
            "sexo",
            "genero",
            "gênero",
        ],
    )

    coluna_idade = localizar_coluna(
        df.columns,
        [
            "idade",
            "faixa_etaria",
            "faixa etária",
            "faixa de idade",
        ],
    )

    coluna_localidade = localizar_coluna(
        df.columns,
        [
            "localidade",
            "bairro",
            "bairros",
            "regiao",
            "região",
            "cidade",
            "municipio",
            "município",
        ],
    )

    coluna_entrevistador = localizar_coluna(
        df.columns,
        [
            "entrevistador",
            "pesquisador",
            "agente",
            "nome_entrevistador",
        ],
    )

    inseridas = 0
    ignoradas = 0
    erros = 0

    sql_insert = text("""
        INSERT INTO entrevistas (
            submission_id,
            pesquisa_id,
            sexo,
            idade,
            localidade,
            entrevistador,
            dados
        )
        VALUES (
            :submission_id,
            :pesquisa_id,
            :sexo,
            :idade,
            :localidade,
            :entrevistador,
            CAST(:dados AS jsonb)
        )
        ON CONFLICT (pesquisa_id, submission_id)
        DO NOTHING
        RETURNING id
    """)

    with engine.begin() as conn:

        for numero_linha, linha in df.iterrows():

            try:
                dados = {
                    coluna: converter_valor_json(valor)
                    for coluna, valor in linha.items()
                }

                submission_id = None

                for campo_id in [
                    "__id",
                    "meta.instanceID",
                    "instanceID",
                    "_uuid",
                    "uuid"
                ]:
                    if campo_id in df.columns:
                        valor_id = linha.get(campo_id)

                        if pd.notna(valor_id) and str(valor_id).strip():
                            submission_id = str(valor_id).strip()
                            break

                if not submission_id:
                    submission_id = criar_submission_id(
                        pesquisa_id,
                        numero_linha,
                        dados
                    )

                sexo = (
                    texto_limpo(linha.get(coluna_sexo))
                    if coluna_sexo else None
                )

                idade = (
                    texto_limpo(linha.get(coluna_idade))
                    if coluna_idade else None
                )

                localidade = (
                    texto_limpo(linha.get(coluna_localidade))
                    if coluna_localidade else "Não informado"
                )

                entrevistador = (
                    texto_limpo(linha.get(coluna_entrevistador))
                    if coluna_entrevistador else "Não informado"
                )

                resultado = conn.execute(
                    sql_insert,
                    {
                        "submission_id": submission_id,
                        "pesquisa_id": pesquisa_id,
                        "sexo": sexo,
                        "idade": idade,
                        "localidade": localidade,
                        "entrevistador": entrevistador,
                        "dados": json.dumps(
                            dados,
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ).fetchone()

                if resultado:
                    inseridas += 1
                else:
                    ignoradas += 1

            except Exception as erro:
                erros += 1
                print(
                    f"ERRO NA LINHA {numero_linha + 2}: {erro}"
                )

    return inseridas, ignoradas, erros


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================

def executar_importacao(
    arquivo,
    cliente_id,
    nome_pesquisa,
    pesquisa_id=None,
    aba=None,
):
    print("\n======================================")
    print("IMPORTADOR EXCEL → IPSENSUS SURVEY")
    print("======================================")

    df_original = preparar_dataframe(
        arquivo,
        nome_aba=aba,
    )

    print(f"Linhas encontradas: {len(df_original)}")
    print(f"Colunas encontradas: {len(df_original.columns)}")

    df = df_original.copy()

    df.columns = [
        str(coluna).strip()
        for coluna in df.columns
    ]

    de_para = {
        str(coluna).strip(): str(coluna).strip()
        for coluna in df.columns
    }

    pesquisa_id_final = criar_ou_localizar_pesquisa(
        nome_pesquisa=nome_pesquisa,
        cliente_id=cliente_id,
        nome_arquivo=Path(arquivo).name,
        pesquisa_id=pesquisa_id,
    )

    print(f"Pesquisa ID: {pesquisa_id_final}")

    perguntas_inseridas = importar_perguntas(
        pesquisa_id_final,
        de_para,
    )

    inseridas, ignoradas, erros = importar_entrevistas(
        df,
        pesquisa_id_final,
    )

    print("\n======================================")
    print("IMPORTAÇÃO FINALIZADA")
    print("======================================")
    print(f"Pesquisa ID: {pesquisa_id_final}")
    print(f"Perguntas novas: {perguntas_inseridas}")
    print(f"Entrevistas inseridas: {inseridas}")
    print(f"Entrevistas já existentes: {ignoradas}")
    print(f"Linhas com erro: {erros}")

    return pesquisa_id_final


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Importa uma pesquisa Excel/CSV para o "
            "dashboard Ipsensus Survey."
        )
    )

    parser.add_argument(
        "--arquivo",
        required=True,
        help="Caminho completo do arquivo Excel ou CSV.",
    )

    parser.add_argument(
        "--cliente-id",
        required=True,
        type=int,
        help="ID do cliente no Supabase.",
    )

    parser.add_argument(
        "--nome-pesquisa",
        required=True,
        help="Nome que aparecerá no dashboard.",
    )

    parser.add_argument(
        "--pesquisa-id",
        type=int,
        default=None,
        help=(
            "ID de uma pesquisa existente. "
            "Omitir para criar uma nova pesquisa."
        ),
    )

    parser.add_argument(
        "--aba",
        default=None,
        help="Nome da aba do Excel. Omitir para usar a primeira.",
    )

    args = parser.parse_args()

    executar_importacao(
        arquivo=args.arquivo,
        cliente_id=args.cliente_id,
        nome_pesquisa=args.nome_pesquisa,
        pesquisa_id=args.pesquisa_id,
        aba=args.aba,
    )


if __name__ == "__main__":
    main()
