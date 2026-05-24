import os
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
from flask import Flask, request, session, redirect

# =========================
# CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = "supersecret"

server = Flask(__name__)
server.secret_key = SECRET_KEY

engine = create_engine(DATABASE_URL)

# =========================
# LOGIN
# =========================
@server.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]

        query = text("""
            SELECT id, cliente_id
            FROM usuarios
            WHERE email = :email AND senha = :senha
        """)

        with engine.connect() as conn:
            result = conn.execute(query, {
                "email": email,
                "senha": senha
            })
            user = result.fetchone()

        if user:
            session["user_id"] = user[0]
            session["cliente_id"] = user[1]
            return redirect("/dashboard")
        else:
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
# DASH
# =========================
app = dash.Dash(
    __name__,
    server=server,
    url_base_pathname="/dashboard/"
)

# =========================
# PROTEGER ROTA
# =========================
@server.before_request
def proteger():
    if request.path.startswith("/dashboard"):
        if "cliente_id" not in session:
            return redirect("/")

# =========================
# LISTA PESQUISAS DO CLIENTE
# =========================
def lista_pesquisas(cliente_id):
    df = pd.read_sql(text("""
        SELECT id, nome
        FROM pesquisas
        WHERE cliente_id = :cliente_id
    """), engine, params={"cliente_id": cliente_id})

    return [{"label": row["nome"], "value": row["id"]} for _, row in df.iterrows()]

# =========================
# CARREGAR DADOS
# =========================
def carregar_dados(pesquisa_id):
    df = pd.read_sql(text("""
        SELECT *
        FROM entrevistas
        WHERE pesquisa_id = :pesquisa_id
    """), engine, params={"pesquisa_id": pesquisa_id})

    if df.empty:
        return df

    df["sexo"] = df["sexo"].str.title()
    df["localidade"] = df["localidade"].str.upper()

    return df

# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.H1("📊 DASHBOARD ELEITORAL"),

    dcc.Dropdown(id="pesquisa"),

    html.Div(id="kpis"),

    dcc.Graph(id="sexo"),
    dcc.Graph(id="bairro"),

    html.Div(id="idade"),
    html.Div(id="entrevistador"),

    html.H3("Resultados das Perguntas"),
    html.Div(id="perguntas")
])

# =========================
# CALLBACK PRINCIPAL
# =========================
@app.callback(
    [
        Output("pesquisa", "options"),
        Output("kpis", "children"),
        Output("sexo", "figure"),
        Output("bairro", "figure"),
        Output("idade", "children"),
        Output("entrevistador", "children"),
        Output("perguntas", "children")
    ],
    Input("pesquisa", "value")
)
def atualizar(pesquisa_id):

    if "cliente_id" not in session:
        return [], "", {}, {}, "", "", ""

    cliente_id = session["cliente_id"]
    options = lista_pesquisas(cliente_id)

    if not pesquisa_id:
        return options, "", {}, {}, "", "", ""

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return options, "Sem dados", {}, {}, "", "", ""

    total = len(df)

    # ================= KPI
    kpi = html.H3(f"Total: {total}")

    # ================= SEXO
    sexo_df = df["sexo"].value_counts().reset_index()
    sexo_df.columns = ["sexo", "qtd"]

    fig_sexo = px.pie(sexo_df, names="sexo", values="qtd")

    # ================= BAIRRO
    bairro = df["localidade"].value_counts().reset_index()
    bairro.columns = ["bairro", "qtd"]

    fig_bairro = px.bar(bairro, x="bairro", y="qtd")

    # ================= IDADE
    idade = df["idade"].value_counts()

    idade_html = [html.Div(f"{i}: {n}") for i, n in idade.items()]

    # ================= ENTREVISTADOR
    ent = df["entrevistador"].value_counts()

    ent_html = [html.Div(f"{i}: {n}") for i, n in ent.items()]

    # ================= PERGUNTAS DINÂMICAS (JSONB)
    perguntas_html = []

    if "dados" in df.columns:
        respostas = df["dados"].dropna()

        all_keys = set()

        for r in respostas:
            all_keys.update(r.keys())

        for key in all_keys:
            vals = respostas.apply(lambda x: x.get(key) if key in x else None)
            contagem = vals.value_counts()

            df_plot = contagem.reset_index()
            df_plot.columns = ["resposta", "qtd"]

            fig = px.bar(df_plot, x="resposta", y="qtd", title=key)

            perguntas_html.append(dcc.Graph(figure=fig))

    return (
        options,
        kpi,
        fig_sexo,
        fig_bairro,
        idade_html,
        ent_html,
        perguntas_html
    )

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)