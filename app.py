import pandas as pd
import psycopg2
from flask import Flask, render_template_string, request, redirect, session
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
# LOGIN
# ==============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]

        conn = conectar()
        df = pd.read_sql(f"""
            SELECT * FROM usuarios
            WHERE usuario = '{usuario}'
        """, conn)

        conn.close()

        # validação segura
        if df.empty:
            return "Usuário não encontrado"

        # pega primeira linha
        user = df.iloc[0]

        # valida senha
        if str(user["senha"]) != str(senha):
            return "Senha incorreta"

        # salva sessão
        session["usuario"] = usuario

        # se existir pesquisa_id, salva
        if "pesquisa_id" in df.columns:
            session["pesquisa_id"] = int(user["pesquisa_id"])

        return redirect("/")

    return """
    <h2>Login</h2>
    <form method="post">
        Usuário: <input name="usuario"><br>
        Senha: <input name="senha" type="password"><br>
        <button type="submit">Entrar</button>
    </form>
    """

# ==============================
# DASHBOARD
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

    conn = conectar()
    df = pd.read_sql("SELECT * FROM dados_pesquisa", conn)
    conn.close()

    # ==============================
    # NORMALIZA COLUNAS (ANTI-ERRO)
    # ==============================
    df.columns = [c.upper() for c in df.columns]

    # ==============================
    # KPIs
    # ==============================
    total = len(df)

    # sexo (se existir)
    if "SEXO" in df.columns:
        sexo = df["SEXO"].value_counts().reset_index()
        sexo.columns = ["SEXO", "TOTAL"]
        sexo["%"] = round(sexo["TOTAL"] / total * 100, 1)
    else:
        sexo = pd.DataFrame()

    # idade (se existir)
    if "IDADE" in df.columns:
        idade = df["IDADE"].value_counts().reset_index()
        idade.columns = ["IDADE", "TOTAL"]
        idade["%"] = round(idade["TOTAL"] / total * 100, 1)
    else:
        idade = pd.DataFrame()

    kpis = html.Div([
        html.H4(f"Amostra Total: {total}"),
        html.H5("Sexo"),
        dash_table.DataTable(data=sexo.to_dict("records")),
        html.H5("Idade"),
        dash_table.DataTable(data=idade.to_dict("records"))
    ])

    # ==============================
    # PERGUNTAS AUTOMÁTICAS
    # ==============================
    perguntas = [c for c in df.columns if c not in ["SEXO", "IDADE"]]

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