import os
import pandas as pd
from sqlalchemy import create_engine
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
from flask import request, session, redirect

# =========================
# CONEXÃO
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# =========================
# APP
# =========================
app = dash.Dash(__name__)
server = app.server
server.secret_key = "segredo"

# =========================
# LOGIN
# =========================
@app.server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = f"""
            SELECT * FROM usuarios
            WHERE email = '{email}' AND senha = '{senha}'
        """

        df = pd.read_sql(query, engine)
df.columns = df.columns.str.strip().str.upper()

print("COLUNAS:", df.columns)

        if not df.empty:
            session["usuario"] = df.iloc[0]["email"]
            return redirect("/")

        return "Login inválido"

    return """
    <h2>Login</h2>
    <form method="post">
        Email: <input name="email"><br>
        Senha: <input name="senha" type="password"><br>
        <button type="submit">Entrar</button>
    </form>
    """

# =========================
# PROTEÇÃO
# =========================
@app.server.before_request
def proteger():
    if request.path == "/login":
        return

    if "usuario" not in session:
        return redirect("/login")

# =========================
# DADOS
# =========================
def carregar_dados():
    pesquisa_id = session.get("pesquisa_id")

    if not pesquisa_id:
        pesquisa_id = 1

    query = f"""
        SELECT *
        FROM entrevistas
        WHERE pesquisa_id = {pesquisa_id}
    """

    df = pd.read_sql(query, engine)
    df = df.fillna("Não informado")

    return df

# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.H1("📊 DASHBOARD ELEITORAL"),

    html.Div(id="kpis"),

    dcc.Dropdown(
        id="filtro-pergunta",
        placeholder="Escolha a pergunta",
        style={"width": "50%"}
    ),

    dcc.Graph(id="grafico-dinamico"),

    html.H3("Entrevistadores"),
    html.Div(id="tabela-entrevistador"),

])

# =========================
# CALLBACK
# =========================
@app.callback(
    [
        Output("kpis", "children"),
        Output("grafico-dinamico", "figure"),
        Output("tabela-entrevistador", "children"),
        Output("filtro-pergunta", "options"),
    ],
    Input("filtro-pergunta", "value")
)
def atualizar(pergunta):

    df = carregar_dados()

    if df.empty:
        return "Sem dados", {}, "", []

    total = len(df)

    # =========================
    # SEXO
    # =========================
    sexo = df["SEXO"].value_counts().reset_index()
    sexo.columns = ["Sexo", "Qtd"]
    sexo["%"] = round((sexo["Qtd"] / total) * 100, 1)

    # =========================
    # IDADE
    # =========================
    idade = df["IDADE"].value_counts().reset_index()
    idade.columns = ["Idade", "Qtd"]
    idade["%"] = round((idade["Qtd"] / total) * 100, 1)

    kpis = html.Div([

        html.H2(f"Amostra Total: {total}"),

        html.Div([
            html.H4("Sexo"),
            html.Table([
                html.Tr([html.Th("Sexo"), html.Th("Qtd"), html.Th("%")])
            ] + [
                html.Tr([
                    html.Td(row["Sexo"]),
                    html.Td(row["Qtd"]),
                    html.Td(f'{row["%"]}%')
                ]) for _, row in sexo.iterrows()
            ])
        ], style={"display": "inline-block", "margin": "20px"}),

        html.Div([
            html.H4("Idade"),
            html.Table([
                html.Tr([html.Th("Idade"), html.Th("Qtd"), html.Th("%")])
            ] + [
                html.Tr([
                    html.Td(row["Idade"]),
                    html.Td(row["Qtd"]),
                    html.Td(f'{row["%"]}%')
                ]) for _, row in idade.iterrows()
            ])
        ], style={"display": "inline-block", "margin": "20px"})

    ])

    # =========================
    # FILTRO PERGUNTAS
    # =========================
    ignorar = [
        "id", "submission_id", "pesquisa_id", "dados",
        "SEXO", "IDADE", "LOCALIDADE", "ENTREVISTADOR",
        "__id", "__system"
    ]

    colunas = [c for c in df.columns if c not in ignorar]
    opcoes = [{"label": c, "value": c} for c in colunas]

    if not pergunta:
        pergunta = colunas[0]

    # =========================
    # GRÁFICO
    # =========================
    graf = df[pergunta].value_counts().reset_index()
    graf.columns = ["categoria", "qtd"]

    graf["%"] = round((graf["qtd"] / graf["qtd"].sum()) * 100, 1)

    fig = px.bar(
        graf,
        x="qtd",
        y="categoria",
        orientation="h",
        text=graf["%"].astype(str) + "%"
    )

    fig.update_traces(textposition="outside")

    # =========================
    # ENTREVISTADOR
    # =========================
    ent = df["ENTREVISTADOR"].value_counts().reset_index()
    ent.columns = ["Entrevistador", "Quantidade"]

    tabela = html.Table([
        html.Tr([html.Th("Entrevistador"), html.Th("Qtd")])
    ] + [
        html.Tr([
            html.Td(row["Entrevistador"]),
            html.Td(row["Quantidade"])
        ]) for _, row in ent.iterrows()
    ])

    return kpis, fig, tabela, opcoes

# =========================
# ETL ENDPOINT
# =========================
@app.server.route("/etl")
def rodar_etl():
    os.system("python etl.py")
    return "ETL executado"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)