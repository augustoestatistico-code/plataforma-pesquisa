import os
import pandas as pd
from sqlalchemy import create_engine
import dash
from dash import dcc, html, Input, Output
import plotly.express as px

# =========================
# CONEXÃO
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# =========================
# LOAD PESQUISAS
# =========================
def load_pesquisas():
    query = "SELECT id, nome FROM pesquisas"
    return pd.read_sql(query, engine)

# =========================
# LOAD DATA
# =========================
def load_data(pesquisa_id):

    query = f"""
        SELECT sexo, idade, localidade, entrevistador
        FROM entrevistas
        WHERE pesquisa_id = {pesquisa_id}
    """

    df = pd.read_sql(query, engine)

    # ================= LIMPEZA =================
    df['sexo'] = df['sexo'].astype(str).str.strip().str.capitalize()
    df['localidade'] = df['localidade'].astype(str).str.strip()
    df['entrevistador'] = df['entrevistador'].astype(str).str.strip()

    df['idade'] = pd.to_numeric(df['idade'], errors='coerce')

    # remover vazios
    df = df.dropna(subset=['localidade'])

    return df
# =========================
# FAIXA ETÁRIA
# =========================
def criar_faixa_idade(df):
    bins = [0, 24, 34, 44, 59, 120]
    labels = ['16-24', '25-34', '35-44', '45-59', '60+']
    df['faixa_idade'] = pd.cut(df['idade'], bins=bins, labels=labels)
    return df

# =========================
# APP
# =========================
app = dash.Dash(__name__)
server = app.server

# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.H1("📊 Dashboard Profissional", style={"textAlign": "center"}),

    # ================= FILTRO PESQUISA =================
    dcc.Dropdown(id="filtro-pesquisa", placeholder="Selecionar Pesquisa"),

    html.Hr(),

    # ================= KPI =================
    html.Div([
        html.Div([
            html.H4("Total"),
            html.H2(id="kpi-total")
        ], style={"width": "25%", "display": "inline-block"}),

        html.Div([
            html.H4("Masculino"),
            html.H2(id="kpi-masc")
        ], style={"width": "25%", "display": "inline-block"}),

        html.Div([
            html.H4("Feminino"),
            html.H2(id="kpi-fem")
        ], style={"width": "25%", "display": "inline-block"}),

        html.Div([
            html.H4("Faixa Etária"),
            html.Div(id="kpi-idade")
        ], style={"width": "25%", "display": "inline-block"}),

    ]),

    html.Hr(),

    # ================= FILTROS =================
    dcc.Dropdown(id="filtro-sexo", multi=True, placeholder="Sexo"),
    dcc.Dropdown(id="filtro-local", multi=True, placeholder="Bairro"),

    html.Hr(),

    # ================= GRÁFICOS =================
    dcc.Graph(id="grafico-bairro"),
    dcc.Graph(id="grafico-entrevistador")

])

# =========================
# CALLBACK PRINCIPAL
# =========================
@app.callback(
    [
        Output("filtro-pesquisa", "options"),
        Output("kpi-total", "children"),
        Output("kpi-masc", "children"),
        Output("kpi-fem", "children"),
        Output("kpi-idade", "children"),
        Output("grafico-bairro", "figure"),
        Output("grafico-entrevistador", "figure"),
        Output("filtro-sexo", "options"),
        Output("filtro-local", "options"),
    ],
    [
        Input("filtro-pesquisa", "value"),
        Input("filtro-sexo", "value"),
        Input("filtro-local", "value"),
    ]
)
def update(pesquisa_id, sexo, local):

    # ================= PESQUISAS =================
    pesquisas = load_pesquisas()
    pesquisa_opts = [
        {"label": p["nome"], "value": p["id"]}
        for _, p in pesquisas.iterrows()
    ]

    if not pesquisa_id:
        return pesquisa_opts, 0, "", "", [], {}, {}, [], []

    df = load_data(pesquisa_id)

    # ================= FILTROS =================
    if sexo:
        df = df[df['sexo'].isin(sexo)]

    if local:
        df = df[df['localidade'].isin(local)]

    df = criar_faixa_idade(df)

    total = len(df)

    # ================= KPI SEXO =================
    masc = len(df[df['sexo'] == 'Masculino'])
    fem = len(df[df['sexo'] == 'Feminino'])

    masc_perc = masc / total if total else 0
    fem_perc = fem / total if total else 0

    # ================= KPI IDADE =================
    idade_counts = df['faixa_idade'].value_counts().sort_index()
    idade_perc = df['faixa_idade'].value_counts(normalize=True).sort_index()

    kpi_idade = [
        html.Div(f"{i}: {idade_counts.get(i,0)} ({idade_perc.get(i,0):.1%})")
        for i in idade_counts.index
    ]

    # ================= GRÁFICO BAIRRO =================
bairro_df = (
    df.groupby('localidade')
    .size()
    .reset_index(name='qtd')
)

bairro_df['perc'] = bairro_df['qtd'] / bairro_df['qtd'].sum()

bairro_df = bairro_df.sort_values('qtd', ascending=True)

fig_bairro = px.bar(
    bairro_df,
    x='qtd',
    y='localidade',
    orientation='h',
    text=bairro_df.apply(lambda x: f"{x['qtd']} ({x['perc']:.1%})", axis=1)
)

fig_bairro.update_layout(
    title="Distribuição por Bairro",
    yaxis_title="Bairro",
    xaxis_title="Entrevistas"
)

    # ================= ENTREVISTADOR =================
prod_df = (
    df.groupby('entrevistador')
    .size()
    .reset_index(name='qtd')
)

prod_df['perc'] = prod_df['qtd'] / prod_df['qtd'].sum()

prod_df = prod_df.sort_values('qtd', ascending=True)

fig_prod = px.bar(
    prod_df,
    x='qtd',
    y='entrevistador',
    orientation='h',
    text=prod_df.apply(lambda x: f"{x['qtd']} ({x['perc']:.1%})", axis=1)
)

fig_prod.update_layout(
    title="Produção por Entrevistador"
)

    # ================= FILTROS DINÂMICOS =================
    sexo_opts = [{"label": s, "value": s} for s in df['sexo'].dropna().unique()]
    local_opts = [{"label": l, "value": l} for l in df['localidade'].dropna().unique()]

    return (
        pesquisa_opts,
        total,
        f"{masc} ({masc_perc:.1%})",
        f"{fem} ({fem_perc:.1%})",
        kpi_idade,
        fig_bairro,
        fig_prod,
        sexo_opts,
        local_opts
    )

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run_server(debug=True)