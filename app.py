import os
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output
import plotly.express as px

from flask import request



# =========================
# CONEXÃO
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# =========================
# CARREGAR DADOS
# =========================
def carregar_dados(pesquisa_id=None):
    query = """
        SELECT 
            pesquisa_id,
            sexo,
            idade,
            localidade,
            entrevistador
        FROM entrevistas
    """

    if pesquisa_id:
        query += f" WHERE pesquisa_id = {pesquisa_id}"

    df = pd.read_sql(text(query), engine)

    # =========================
    # LIMPEZA (ESSENCIAL)
    # =========================
    df["sexo"] = df["sexo"].astype(str).str.strip().str.title()
    df["localidade"] = df["localidade"].astype(str).str.strip().str.upper()
    df["entrevistador"] = df["entrevistador"].astype(str).str.replace("ENTREVISTADOR", "", regex=False).str.strip()
    df["idade"] = df["idade"].astype(str).str.strip()

    return df

# =========================
# APP
# =========================
app = dash.Dash(__name__)
server = app.server

# =========================
# LISTA DE PESQUISAS
# =========================
def lista_pesquisas():
    df = pd.read_sql("SELECT DISTINCT pesquisa_id FROM entrevistas ORDER BY pesquisa_id", engine)
    return [{"label": f"Pesquisa {i}", "value": i} for i in df["pesquisa_id"]]

# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.H1("📊 DASHBOARD ELEITORAL PROFISSIONAL"),

    dcc.Dropdown(
        id="filtro-pesquisa",
        options=lista_pesquisas(),
        placeholder="Selecione a pesquisa"
    ),

    html.Br(),

    html.Div(id="kpis"),

    html.Br(),

    dcc.Graph(id="grafico-bairro"),

    dcc.Graph(id="grafico-entrevistador"),
])

# =========================
# CALLBACK
# =========================
@app.callback(
    [
        Output("kpis", "children"),
        Output("grafico-bairro", "figure"),
        Output("grafico-entrevistador", "figure"),
    ],
    Input("filtro-pesquisa", "value")
)
def atualizar(pesquisa_id):

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return "Sem dados", {}, {}

    total = len(df)

    # =========================
    # SEXO
    # =========================
    sexo = df["sexo"].value_counts()

    masc = sexo.get("Masculino", 0)
    fem = sexo.get("Feminino", 0)

    masc_pct = round((masc / total) * 100, 1) if total else 0
    fem_pct = round((fem / total) * 100, 1) if total else 0

    # =========================
    # FAIXA ETÁRIA (JÁ TEXTO)
    # =========================
    ordem = [
        "16 a 24 anos",
        "25 a 34 anos",
        "35 a 44 anos",
        "45 a 59 anos",
        "60 anos ou mais"
    ]

    faixa = df["idade"].value_counts()
    faixa = faixa.reindex(ordem, fill_value=0)

    faixa_html = []
    for f in faixa.index:
        n = faixa[f]
        pct = round((n / total) * 100, 1)
        faixa_html.append(html.Div(f"{f}: {n} ({pct}%)"))

    # =========================
    # KPI
    # =========================
    kpis = html.Div([
        html.H3(f"Total Entrevistas: {total}"),

        html.Div([
            html.Div(f"Masculino: {masc} ({masc_pct}%)"),
            html.Div(f"Feminino: {fem} ({fem_pct}%)"),
        ]),

        html.Br(),

        html.Div([
            html.H4("Faixa Etária"),
            *faixa_html
        ])
    ])

    # =========================
    # BAIRRO
    # =========================
    bairro = df["localidade"].value_counts().reset_index()
    bairro.columns = ["bairro", "qtd"]

    bairro["pct"] = (bairro["qtd"] / total * 100).round(1)

    fig_bairro = px.bar(
        bairro,
        x="qtd",
        y="bairro",
        orientation="h",
        text=bairro["qtd"].astype(str) + " (" + bairro["pct"].astype(str) + "%)"
    )

    fig_bairro.update_layout(
        title="Entrevistas por Bairro",
        yaxis={'categoryorder': 'total ascending'}
    )

    # =========================
    # ENTREVISTADOR
    # =========================
    ent = df["entrevistador"].value_counts().reset_index()
    ent.columns = ["entrevistador", "qtd"]

    ent["pct"] = (ent["qtd"] / total * 100).round(1)

    fig_ent = px.bar(
        ent,
        x="qtd",
        y="entrevistador",
        orientation="h",
        text=ent["qtd"].astype(str) + " (" + ent["pct"].astype(str) + "%)"
    )

    fig_ent.update_layout(
        title="Produção por Entrevistador",
        yaxis={'categoryorder': 'total ascending'}
    )

    return kpis, fig_bairro, fig_ent


@app.server.route("/etl")
def rodar_etl():
    token = request.args.get("token")

    if token != "123456":
        return "Acesso negado", 403

    os.system("python etl.py")
    return "ETL executado com sucesso"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)