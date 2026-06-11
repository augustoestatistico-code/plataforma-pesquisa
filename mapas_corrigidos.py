import os
import json
import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
from sqlalchemy import create_engine, text

# =====================================================
# CONFIGURAÇÕES
# =====================================================

DATABASE_URL = os.getenv("DATABASE_URL")

PESQUISA_ID = 6

ARQUIVO_CORRIGIDO = r"C:\PLATAFORMA_PESQUISA\Arquivos Pesquisas Corrigidas\GOV_NUNES_FREIRE_28MAIO26.xlsx"

PASTA_SAIDA = r"C:\PLATAFORMA_PESQUISA\Arquivos Pesquisas Corrigidas\base\mapas"

os.makedirs(PASTA_SAIDA, exist_ok=True)

engine = create_engine(DATABASE_URL)


# =====================================================
# FUNÇÕES
# =====================================================

def normalizar_json(valor):
    if isinstance(valor, dict):
        return valor

    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except:
            return {}

    return {}


def extrair_lat_lon(dados):
    lat = (
        dados.get("latitude_melhor")
        or dados.get("lat_final")
        or dados.get("lat_inicio")
    )

    lon = (
        dados.get("longitude_melhor")
        or dados.get("lon_final")
        or dados.get("lon_inicio")
    )

    if (not lat or not lon) and isinstance(dados.get("gps_final"), dict):
        coords = dados["gps_final"].get("coordinates", [])
        if len(coords) >= 2:
            lon = coords[0]
            lat = coords[1]

    try:
        return float(lat), float(lon)
    except:
        return None, None


def cor_categoria(valor):
    valor = str(valor).strip().lower()

    cores = {
        "aprova": "green",
        "ótima": "green",
        "otima": "green",
        "boa": "blue",
        "regular": "orange",
        "ruim": "red",
        "péssima": "darkred",
        "pessima": "darkred",
        "desaprova": "red",
        "não sabe": "gray",
        "nao sabe": "gray",
        "ns/nr": "gray",
        "não informado": "gray"
    }

    return cores.get(valor, "purple")


# =====================================================
# 1. CARREGAR DADOS DO DASHBOARD / SUPABASE
# =====================================================

df_db = pd.read_sql(
    text("""
        SELECT
            id,
            submission_id,
            pesquisa_id,
            sexo,
            idade,
            localidade,
            entrevistador,
            dados
        FROM entrevistas
        WHERE pesquisa_id = :pesquisa_id
    """),
    engine,
    params={"pesquisa_id": PESQUISA_ID}
)

print("Entrevistas no banco:", len(df_db))


# =====================================================
# 2. EXPANDIR JSON DO BANCO
# =====================================================

dados_normalizados = df_db["dados"].apply(normalizar_json)
json_df = pd.json_normalize(dados_normalizados)

df_base = pd.concat(
    [
        df_db.drop(columns=["dados"]),
        json_df
    ],
    axis=1
)

# Extrair latitude e longitude
lat_lon = dados_normalizados.apply(extrair_lat_lon)
df_base["lat"] = lat_lon.apply(lambda x: x[0])
df_base["lon"] = lat_lon.apply(lambda x: x[1])

df_base = df_base.dropna(subset=["lat", "lon"])

print("Entrevistas com GPS:", len(df_base))


# =====================================================
# 3. CARREGAR ARQUIVO CORRIGIDO
# =====================================================
xls = pd.ExcelFile(ARQUIVO_CORRIGIDO)

print("ABAS DO ARQUIVO:")
print(xls.sheet_names)

df_corrigido = pd.read_excel(
    ARQUIVO_CORRIGIDO,
    sheet_name="base"
)

print("COLUNAS DO EXCEL CORRIGIDO:")
print(df_corrigido.columns.tolist())

# =====================================================
# 4. DEFINIR CHAVE DE JUNÇÃO
# =====================================================


df_corrigido["meta-instanceID"] = (
    df_corrigido["meta-instanceID"]
    .astype(str)
    .str.strip()
)

df_base["submission_id"] = (
    df_base["submission_id"]
    .astype(str)
    .str.strip()
)


# =====================================================
# 5. JOIN BASE DASHBOARD + ARQUIVO CORRIGIDO
# =====================================================
df_final = df_base.merge(
    df_corrigido,
    left_on="submission_id",
    right_on="meta-instanceID",
    how="left",
    suffixes=("", "_corrigido")
)

df_final["KEY"] = df_final["submission_id"]

print("Base dashboard:", len(df_base))
print("Base corrigida:", len(df_corrigido))
print("Entrevistas encontradas:", df_final["meta-instanceID"].notna().sum())


print("Base final:", len(df_final))


# =====================================================
# 6. MAPA DE PONTOS GERAL
# =====================================================

centro = [df_final["lat"].mean(), df_final["lon"].mean()]

mapa_pontos = folium.Map(
    location=centro,
    zoom_start=12,
    tiles="CartoDB positron"
)

cluster = MarkerCluster().add_to(mapa_pontos)

for _, row in df_final.iterrows():
    popup = f"""
    <b>ID:</b> {row.get('id', '')}<br>
    <b>Localidade:</b> {row.get('localidade', '')}<br>
    <b>Entrevistador:</b> {row.get('entrevistador', '')}<br>
    <b>Sexo:</b> {row.get('sexo', '')}<br>
    <b>Idade:</b> {row.get('idade', '')}
    """

    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=6,
        color="blue",
        fill=True,
        fill_opacity=0.75,
        popup=folium.Popup(popup, max_width=350)
    ).add_to(cluster)

mapa_pontos.save(os.path.join(PASTA_SAIDA, "01_mapa_pontos_geral.html"))


# =====================================================
# 7. MAPA DE CALOR GERAL
# =====================================================

mapa_calor = folium.Map(
    location=centro,
    zoom_start=12,
    tiles="CartoDB dark_matter"
)

HeatMap(
    df_final[["lat", "lon"]].values.tolist(),
    radius=18,
    blur=15,
    min_opacity=0.35
).add_to(mapa_calor)

mapa_calor.save(os.path.join(PASTA_SAIDA, "02_mapa_calor_geral.html"))


# =====================================================
# 8. MAPA TEMÁTICO POR PERGUNTA/KPI
# =====================================================
# Altere aqui para a pergunta corrigida ou KPI desejado.
# Exemplo:
# VARIAVEL_MAPA = "avaliacao_administracao_corrigida"
# VARIAVEL_MAPA = "AVAL_ADM1"
# VARIAVEL_MAPA = "kpi_aprovacao"

VARIAVEL_MAPA = "AVAL_ADM1"

if VARIAVEL_MAPA in df_final.columns:

    mapa_tematico = folium.Map(
        location=centro,
        zoom_start=12,
        tiles="CartoDB positron"
    )

    for _, row in df_final.iterrows():
        resposta = row.get(VARIAVEL_MAPA, "Não informado")
        cor = cor_categoria(resposta)

        popup = f"""
        <b>Localidade:</b> {row.get('localidade', '')}<br>
        <b>Entrevistador:</b> {row.get('entrevistador', '')}<br>
        <b>{VARIAVEL_MAPA}:</b> {resposta}
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=7,
            color=cor,
            fill=True,
            fill_color=cor,
            fill_opacity=0.8,
            popup=folium.Popup(popup, max_width=350)
        ).add_to(mapa_tematico)

    mapa_tematico.save(
        os.path.join(PASTA_SAIDA, f"03_mapa_tematico_{VARIAVEL_MAPA}.html")
    )

else:
    print(f"ATENÇÃO: variável {VARIAVEL_MAPA} não existe na base final.")


# =====================================================
# 9. SALVAR BASE FINAL UNIFICADA
# =====================================================

df_final.to_excel(
    os.path.join(PASTA_SAIDA, "base_final_com_corrigidos.xlsx"),
    index=False
)

print("Mapas gerados em:", PASTA_SAIDA)
