import os
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
from flask import Flask, request, session, redirect
import urllib.parse

# =========================
# CONFIG
# =========================
server = Flask(__name__)
server.secret_key = "supersecretkey"

# conexão (Render usa DATABASE_URL)
DATABASE_URL = urllib.parse.unquote(os.getenv("DATABASE_URL"))
engine = create_engine(DATABASE_URL)
print("DATABASE:", engine.connect().execute(text("SELECT 1")).fetchone())

# =========================
# LOGIN
# =========================
@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = """
            SELECT * FROM usuarios
            WHERE email = :email AND senha = :senha
        """

        user = pd.read_sql(text(query), engine, params={
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
# PROTEÇÃO
# =========================
@server.before_request
def proteger():
    if request.path.startswith("/_dash"):
        return
    if request.path == "/login":
        return
    if "user" not in session:
        return redirect("/login")

# =========================
# FUNÇÕES DADOS
# =========================
def get_pesquisas(cliente_id):
    query = """
        SELECT id, nome
        FROM pesquisas
        WHERE cliente_id = :cliente_id
    """
    return pd.read_sql(text(query), engine, params={"cliente_id": cliente_id})


def carregar_dados(cliente_id, pesquisa_id=None):

    query = """
        SELECT 
            e.pesquisa_id,
            e.sexo,
            e.idade,
            e.localidade,
            e.entrevistador
        FROM entrevistas e
        JOIN pesquisas p ON e.pesquisa_id = p.id
        WHERE p.cliente_id = :cliente_id
    """

    params = {"cliente_id": cliente_id}

    if pesquisa_id:
        query += " AND e.pesquisa_id = :pesquisa_id"
        params["pesquisa_id"] = pesquisa_id

    df = pd.read_sql(text(query), engine, params=params)

    print("TOTAL:", len(df))

    if df.empty:
        print("⚠️ SEM DADOS")

    if not df.empty:
        df["sexo"] = df["sexo"].astype(str).str.strip().str.title()
        df["localidade"] = df["localidade"].astype(str).str.strip().str.upper()
        df["entrevistador"] = df["entrevistador"].astype(str).str.replace("ENTREVISTADOR", "", regex=False).str.strip()
        df["idade"] = df["idade"].astype(str).str.strip()

    return df

# =========================
# DASH APP
# =========================
app = dash.Dash(__name__, server=server, url_base_pathname="/")

app.layout = html.Div([
    html.H2("Dashboard de Pesquisa"),

    dcc.Dropdown(id="filtro-pesquisa", placeholder="Selecione a pesquisa"),

    dcc.Graph(id="grafico-sexo"),
])

# =========================
# DROPDOWN
# =========================
@app.callback(
    Output("filtro-pesquisa", "options"),
    Input("filtro-pesquisa", "id")
)
def carregar_opcoes(_):
    cliente_id = session.get("cliente_id")

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
    Input("filtro-pesquisa", "value")
)
def atualizar(pesquisa_id):

    cliente_id = session.get("cliente_id")

    df = carregar_dados(cliente_id, pesquisa_id)

    if df.empty:
        return px.bar(title="Sem dados")

    fig = px.histogram(df, x="sexo", title="Distribuição por Sexo")

    return fig

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)