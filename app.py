import pandas as pd
import psycopg2
import json

from flask import Flask, request, redirect, session
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px

# =========================
# CONFIG
# =========================

app = Flask(__name__)
app.secret_key = "segredo123"

# conexão supabase (ALTERE)
conn = psycopg2.connect(
    host="SEU_HOST",
    database="SEU_DB",
    user="SEU_USER",
    password="SEU_PASSWORD"
)

# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        df = pd.read_sql(f"""
        SELECT * FROM usuarios
        WHERE email = '{email}' AND senha = '{senha}'
        """, conn)

        if not df.empty:
            session["cliente_id"] = int(df.iloc[0]["cliente_id"])
            session["logo"] = df.iloc[0]["logo"]

            # pega pesquisa do cliente
            pesquisa = pd.read_sql(f"""
            SELECT * FROM pesquisas
            WHERE cliente_id = {session["cliente_id"]}
            LIMIT 1
            """, conn)

            if not pesquisa.empty:
                session["pesquisa_id"] = int(pesquisa.iloc[0]["id"])

            return redirect("/")

        return "Login inválido"

    return """
    <form method="post">
        Email: <input name="email"><br>
        Senha: <input name="senha" type="password"><br>
        <button type="submit">Entrar</button>
    </form>
    """

# =========================
# DASH
# =========================

dash_app = dash.Dash(
    __name__,
    server=app,
    url_base_pathname="/"
)

dash_app.layout = html.Div([
    html.H2("Dashboard Pesquisa"),

    dcc.Interval(id="interval", interval=2000, n_intervals=0),

    html.Div(id="kpis"),
    dcc.Dropdown(id="pergunta"),
    dcc.Graph(id="grafico"),

    dash_table.DataTable(id="tabela")
])

# =========================
# CALLBACK
# =========================

@dash_app.callback(
    [
        Output("kpis", "children"),
        Output("pergunta", "options"),
        Output("grafico", "figure"),
        Output("tabela", "data")
    ],
    [Input("interval", "n_intervals")]
)
def atualizar(n):

    if "pesquisa_id" not in session:
        return "Faça login em /login", [], {}, []

    # =========================
    # LER DADOS
    # =========================
    df = pd.read_sql(f"""
    SELECT * FROM entrevistas
    WHERE pesquisa_id = {session['pesquisa_id']}
    """, conn)

    if df.empty:
        return "Sem dados (rode /etl)", [], {}, []

    # =========================
    # JSON ODK
    # =========================
    df_json = pd.json_normalize(df["dados"].apply(json.loads))

    # =========================
    # KPIs
    # =========================
    total = len(df_json)

    kpis = html.Div([
        html.H3(f"Amostra: {total}")
    ])

    # =========================
    # LISTA DE PERGUNTAS DINÂMICAS
    # =========================
    perguntas = df_json.columns.tolist()

    opcoes = [{"label": p, "value": p} for p in perguntas]

    if not perguntas:
        return kpis, [], {}, []

    pergunta = perguntas[0]

    # =========================
    # GRÁFICO
    # =========================
    contagem = df_json[pergunta].value_counts(normalize=True) * 100
    contagem = contagem.reset_index()
    contagem.columns = ["resposta", "percentual"]

    fig = px.bar(
        contagem,
        x="resposta",
        y="percentual",
        text=contagem["percentual"].round(1)
    )

    fig.update_traces(
        texttemplate="%{text}%",
        textposition="outside"
    )

    # =========================
    # TABELA
    # =========================
    tabela = df_json.head(50).to_dict("records")

    return kpis, opcoes, fig, tabela


# =========================
# ETL (SIMPLES MOCK)
# =========================

@app.route("/etl")
def etl():
    return "ETL OK (implementar integração ODK aqui)"

# =========================
# RUN
# =========================

server = app