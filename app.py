import os
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
from flask import Flask, request, redirect, session

# =========================
# CONFIG SERVIDOR
# =========================
server = Flask(__name__)
server.secret_key = "secret123"

# =========================
# CONEXÃO DATABASE (Render já tem DATABASE_URL)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# =========================
# LOGIN
# =========================
@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = f"""
            SELECT id, cliente_id 
            FROM usuarios 
            WHERE email = '{email}' 
            AND senha = '{senha}'
        """

        df = pd.read_sql(text(query), engine)

        if not df.empty:
            session["usuario_id"] = int(df.iloc[0]["id"])
            session["cliente_id"] = int(df.iloc[0]["cliente_id"])
            return redirect("/")
        else:
            return "Login inválido"

    return """
        <form method="post">
            <input name="email" placeholder="email"><br>
            <input name="senha" type="password" placeholder="senha"><br>
            <button type="submit">Entrar</button>
        </form>
    """

# =========================
# CARREGAR DADOS
# =========================
def carregar_dados(cliente_id):
    query = f"""
        SELECT 
            e.pesquisa_id,
            e.sexo,
            e.idade,
            e.localidade,
            e.entrevistador
        FROM entrevistas e
        JOIN pesquisas p ON e.pesquisa_id = p.id
        WHERE p.cliente_id = {cliente_id}
    """

    df = pd.read_sql(text(query), engine)

    if df.empty:
        return df

    # LIMPEZA
    df["sexo"] = df["sexo"].astype(str).str.strip().str.title()
    df["idade"] = df["idade"].astype(str).str.strip()
    df["localidade"] = df["localidade"].astype(str).str.upper()

    return df

# =========================
# DASH APP
# =========================
app = dash.Dash(__name__, server=server, suppress_callback_exceptions=True)

app.layout = html.Div([

    html.H2("Dashboard de Pesquisa"),

    dcc.Interval(id="interval", interval=5000),

    html.Div(id="kpis"),

    html.Br(),

    dcc.Graph(id="grafico_sexo"),
    dcc.Graph(id="grafico_idade"),

])

# =========================
# CALLBACK
# =========================
@app.callback(
    Output("kpis", "children"),
    Output("grafico_sexo", "figure"),
    Output("grafico_idade", "figure"),
    Input("interval", "n_intervals")
)
def atualizar(n):

    if "cliente_id" not in session:
        return "Faça login em /login", {}, {}

    df = carregar_dados(session["cliente_id"])

    # 🔥 DEBUG AQUI
    print("COLUNAS:", df.columns)
    print("TOTAL:", len(df))
    print(df.head())

    if df.empty:
        return "Sem dados", {}, {}

    # =========================
    # KPI TOTAL
    # =========================
    total = len(df)

    # =========================
    # SEXO
    # =========================
    sexo = df["sexo"].value_counts().reset_index()
    sexo.columns = ["sexo", "qtd"]
    sexo["perc"] = (sexo["qtd"] / total * 100).round(1)

    fig_sexo = px.bar(
        sexo,
        x="sexo",
        y="qtd",
        text=sexo["perc"].astype(str) + "%"
    )

    # =========================
    # IDADE
    # =========================
    idade = df["idade"].value_counts().reset_index()
    idade.columns = ["idade", "qtd"]
    idade["perc"] = (idade["qtd"] / total * 100).round(1)

    fig_idade = px.bar(
        idade,
        x="idade",
        y="qtd",
        text=idade["perc"].astype(str) + "%"
    )

    # =========================
    # KPI TABELA
    # =========================
    tabela = html.Div([
        html.H4(f"Amostra Total: {total}"),

        html.H5("Sexo"),
        html.Table([
            html.Tr([html.Th("Sexo"), html.Th("Qtd"), html.Th("%")])] +
            [html.Tr([html.Td(r["sexo"]), html.Td(r["qtd"]), html.Td(f"{r['perc']}%")]) for _, r in sexo.iterrows()]
        ),

        html.H5("Idade"),
        html.Table([
            html.Tr([html.Th("Idade"), html.Th("Qtd"), html.Th("%")])] +
            [html.Tr([html.Td(r["idade"]), html.Td(r["qtd"]), html.Td(f"{r['perc']}%")]) for _, r in idade.iterrows()]
        )
    ])

    return tabela, fig_sexo, fig_idade

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)