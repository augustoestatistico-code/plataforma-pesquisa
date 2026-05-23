import pandas as pd
import psycopg2
from flask import Flask, request, redirect, session
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import os

# ==============================
# CONFIG
# ==============================
app = Flask(__name__)
app.secret_key = "segredo123"

DATABASE_URL = os.getenv("DATABASE_URL")

def conectar():
    return psycopg2.connect(DATABASE_URL)

# ==============================
# LOGIN (CORRIGIDO)
# ==============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        conn = conectar()

        df = pd.read_sql(f"""
            SELECT * FROM usuarios
            WHERE email = '{email}'
        """, conn)

        conn.close()

        if df.empty:
            return "Usuário não encontrado"

        user = df.iloc[0]

        if str(user["senha"]) != str(senha):
            return "Senha incorreta"

        # salva sessão
        session["usuario"] = email
        session["cliente_id"] = int(user["cliente_id"])
        session["logo"] = user["logo"]

        return redirect("/")

    return """
    <h2>Login</h2>
    <form method="post">
        Email: <input name="email"><br>
        Senha: <input name="senha" type="password"><br>
        <button type="submit">Entrar</button>
    </form>
    """

# ==============================
# DASH
# ==============================
dash_app = dash.Dash(__name__, server=app, url_base_pathname="/")

dash_app.layout = html.Div([
    html.H2("Dashboard Pesquisa"),

    dcc.Dropdown(id="pergunta"),

    html.Div(id="kpis"),
    dcc.Graph(id="grafico"),
    dash_table.DataTable(id="tabela")
])

# ==============================
# CALLBACK
# ==============================
@dash_app.callback(
    [Output("kpis", "children"),
     Output("grafico", "figure"),
     Output("tabela", "data"),
     Output("pergunta", "options")],
    [Input("pergunta", "value")]
)
def atualizar(pergunta):

    if "cliente_id" not in session:
        return "Faça login", {}, [], []

    cliente_id = session["cliente_id"]

    conn = conectar()

    # 🔗 BUSCA PESQUISA DO CLIENTE
    pesquisa = pd.read_sql(f"""
        SELECT id FROM pesquisas
        WHERE cliente_id = {cliente_id}
        LIMIT 1
    """, conn)

    if pesquisa.empty:
        conn.close()
        return "Sem pesquisa", {}, [], []

    pesquisa_id = int(pesquisa.iloc[0]["id"])

    # 🔗 BUSCA DADOS
    df = pd.read_sql(f"""
        SELECT * FROM dados_pesquisa
        WHERE pesquisa_id = {pesquisa_id}
    """, conn)

    conn.close()

    if df.empty:
        return "Sem dados", {}, [], []

    # normaliza
    df.columns = [c.upper() for c in df.columns]

    total = len(df)

    # ==============================
    # KPIs
    # ==============================
    sexo = pd.DataFrame()
    idade = pd.DataFrame()

    if "SEXO" in df.columns:
        sexo = df["SEXO"].value_counts().reset_index()
        sexo.columns = ["SEXO", "TOTAL"]
        sexo["%"] = round(sexo["TOTAL"] / total * 100, 1)

    if "IDADE" in df.columns:
        idade = df["IDADE"].value_counts().reset_index()
        idade.columns = ["IDADE", "TOTAL"]
        idade["%"] = round(idade["TOTAL"] / total * 100, 1)

    kpis = html.Div([
        html.H4(f"Amostra Total: {total}"),
        html.H5("Sexo"),
        dash_table.DataTable(data=sexo.to_dict("records")),
        html.H5("Idade"),
        dash_table.DataTable(data=idade.to_dict("records"))
    ])

    # ==============================
    # PERGUNTAS
    # ==============================
    perguntas = [c for c in df.columns if c not in ["SEXO", "IDADE", "PESQUISA_ID"]]

    opcoes = [{"label": p, "value": p} for p in perguntas]

    if not pergunta:
        pergunta = perguntas[0]

    # ==============================
    # GRÁFICO
    # ==============================
    graf = df[pergunta].value_counts().reset_index()
    graf.columns = ["Resposta", "Total"]
    graf["%"] = round(graf["Total"] / total * 100, 1)

    fig = px.bar(
        graf,
        x="Resposta",
        y="Total",
        text=graf["%"].astype(str) + "%"
    )

    fig.update_traces(textposition="outside")

    return kpis, fig, graf.to_dict("records"), opcoes

# ==============================
# RUN
# ==============================
server = app

if __name__ == "__main__":
    app.run(debug=True)