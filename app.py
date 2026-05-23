import os
import pandas as pd
import urllib.parse
from sqlalchemy import create_engine, text

import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px

from flask import Flask, request, session, redirect, jsonify

# =========================
# FLASK
# =========================
server = Flask(__name__)
server.secret_key = "supersecretkey"

# =========================
# DATABASE
# =========================
DATABASE_URL = urllib.parse.unquote(os.getenv("DATABASE_URL"))
engine = create_engine(DATABASE_URL)


# =========================
# LOGIN
# =========================
@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = text("""
            SELECT id, email, cliente_id
            FROM usuarios
            WHERE email = :email AND senha = :senha
        """)

        user = pd.read_sql(query, engine, params={
            "email": email,
            "senha": senha
        })

        if not user.empty:
            session["user"] = email
            session["cliente_id"] = int(user.iloc[0]["cliente_id"])
            return redirect("/")
        else:
            return "Login inválido"

    return """
        <h2>Login</h2>
        <form method="post">
            <input name="email" placeholder="Email"/>
            <input name="senha" type="password" placeholder="Senha"/>
            <button type="submit">Entrar</button>
        </form>
    """


# =========================
# ENDPOINT PARA DASH PEGAR SESSÃO
# =========================
@server.route("/me")
def me():
    return jsonify({
        "user": session.get("user"),
        "cliente_id": session.get("cliente_id")
    })


# =========================
# PROTEÇÃO
# =========================
@server.before_request
def proteger():
    if request.path.startswith("/_dash"):
        return
    if request.path == "/login":
        return
    if request.path == "/me":
        return
    if "user" not in session:
        return redirect("/login")


# =========================
# FUNÇÕES
# =========================
def get_pesquisas(cliente_id):
    query = text("""
        SELECT id, nome
        FROM pesquisas
        WHERE cliente_id = :cliente_id
    """)
    return pd.read_sql(query, engine, params={"cliente_id": cliente_id})


def carregar_dados(cliente_id, pesquisa_id=None):

    query = """
        SELECT 
            e.pesquisa_id,
            e.sexo,
            e.idade,
            e.localidade,
            e.entrevistador
        FROM entrevistas e
        JOIN pesquisas p ON p.id = e.pesquisa_id
        WHERE p.cliente_id = :cliente_id
    """

    params = {"cliente_id": cliente_id}

    if pesquisa_id:
        query += " AND e.pesquisa_id = :pesquisa_id"
        params["pesquisa_id"] = pesquisa_id

    df = pd.read_sql(text(query), engine, params=params)

    if df.empty:
        return df

    df["sexo"] = df["sexo"].astype(str).str.strip().str.title()
    df["localidade"] = df["localidade"].astype(str).str.strip().str.upper()
    df["entrevistador"] = df["entrevistador"].astype(str).str.replace("ENTREVISTADOR", "", regex=False).str.strip()

    return df


# =========================
# DASH APP
# =========================
app = dash.Dash(
    __name__,
    server=server,
    url_base_pathname="/",
    suppress_callback_exceptions=True
)

app.layout = html.Div([

    dcc.Location(id="url"),

    dcc.Store(id="store-cliente"),

    html.H2("Dashboard de Pesquisa"),

    dcc.Dropdown(id="filtro-pesquisa"),

    dcc.Graph(id="grafico-sexo"),
])


# =========================
# PEGAR USUÁRIO REAL DO FLASK
# =========================
@app.callback(
    Output("store-cliente", "data"),
    Input("url", "pathname")
)
def carregar_sessao(_):
    r = server.test_client().get("/me")  # pega sessão Flask corretamente
    data = r.get_json()
    return data.get("cliente_id")


# =========================
# DROPDOWN PESQUISAS
# =========================
@app.callback(
    Output("filtro-pesquisa", "options"),
    Input("store-cliente", "data")
)
def carregar_opcoes(cliente_id):

    if not cliente_id:
        return []

    df = get_pesquisas(cliente_id)

    return [
        {"label": row["nome"], "value": row["id"]}
        for _, row in df.iterrows()
    ]


# =========================
# GRAFICO
# =========================
@app.callback(
    Output("grafico-sexo", "figure"),
    Input("filtro-pesquisa", "value"),
    State("store-cliente", "data")
)
def atualizar(pesquisa_id, cliente_id):

    if not cliente_id:
        return px.bar(title="Sem cliente logado")

    df = carregar_dados(cliente_id, pesquisa_id)

    if df.empty:
        return px.bar(title="Sem dados")

    return px.histogram(df, x="sexo", title="Distribuição por Sexo")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)