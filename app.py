import pandas as pd
import psycopg2
from flask import Flask, request, redirect, session
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import os

# =========================
# CONFIG
# =========================
DB_URL = os.getenv("DATABASE_URL")

server = Flask(__name__)
server.secret_key = "segredo_super"

# =========================
# FUNÇÃO BANCO
# =========================
def carregar_dados():
    conn = psycopg2.connect(DB_URL)
    
    query = """
    SELECT *
    FROM respostas
    """
    
    df = pd.read_sql(query, conn)
    conn.close()

    # PADRONIZA COLUNAS (EVITA ERRO PRA SEMPRE)
    df.columns = df.columns.str.strip().str.upper()

    return df


# =========================
# LOGIN
# =========================
@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        senha = request.form.get("senha")

        df = carregar_dados()

        # DEBUG
        print(df.columns)

        if not df.empty and "PESQUISA_ID" in df.columns:
            session["logado"] = True
            session["pesquisa_id"] = int(df.iloc[0]["PESQUISA_ID"])
            return redirect("/")
        else:
            return "Erro: coluna PESQUISA_ID não encontrada"

    return """
    <h2>Login</h2>
    <form method="post">
        <input type="password" name="senha" placeholder="Senha"/>
        <input type="submit"/>
    </form>
    """


# =========================
# DASH
# =========================
app = dash.Dash(__name__, server=server, url_base_pathname="/")

app.layout = html.Div([
    
    html.H2("📊 Dashboard Pesquisa"),

    dcc.Dropdown(id="filtro_pergunta", placeholder="Selecione pergunta"),

    html.Div(id="kpis"),

    dcc.Graph(id="grafico")

])


# =========================
# CALLBACK
# =========================
@app.callback(
    Output("kpis", "children"),
    Output("grafico", "figure"),
    Input("filtro_pergunta", "value")
)
def atualizar(pergunta):

    df = carregar_dados()

    # GARANTIA TOTAL
    df.columns = df.columns.str.strip().str.upper()

    # =========================
    # TRATAMENTO DE SEGURANÇA
    # =========================
    if "SEXO" not in df.columns:
        df["SEXO"] = "Não informado"

    if "IDADE" not in df.columns:
        df["IDADE"] = "Não informado"

    # =========================
    # KPIs
    # =========================
    total = len(df)

    sexo = df["SEXO"].value_counts(normalize=True).reset_index()
    sexo.columns = ["SEXO", "%"]
    sexo["%"] = (sexo["%"] * 100).round(1)

    idade = df["IDADE"].value_counts(normalize=True).reset_index()
    idade.columns = ["IDADE", "%"]
    idade["%"] = (idade["%"] * 100).round(1)

    kpis = html.Div([

        html.H3(f"Amostra Total: {total}"),

        html.H4("Sexo"),
        dash_table.DataTable(
            data=sexo.to_dict("records"),
            columns=[{"name": i, "id": i} for i in sexo.columns]
        ),

        html.H4("Idade"),
        dash_table.DataTable(
            data=idade.to_dict("records"),
            columns=[{"name": i, "id": i} for i in idade.columns]
        )
    ])

    # =========================
    # PERGUNTAS AUTOMÁTICAS
    # =========================
    perguntas = [
        col for col in df.columns
        if col not in ["ID", "PESQUISA_ID", "SEXO", "IDADE", "LOCALIDADE"]
    ]

    # =========================
    # GRÁFICO
    # =========================
    if pergunta and pergunta in df.columns:

        graf = df[pergunta].value_counts(normalize=True).reset_index()
        graf.columns = ["Resposta", "%"]
        graf["%"] = graf["%"] * 100

        fig = px.bar(
            graf,
            x="Resposta",
            y="%",
            text=graf["%"].apply(lambda x: f"{x:.1f}%")
        )

        fig.update_traces(textposition="outside")

    else:
        fig = px.bar(title="Selecione uma pergunta")

    return kpis, fig


# =========================
# PROTEÇÃO LOGIN
# =========================
@server.before_request
def proteger():
    if request.path.startswith("/_dash"):
        return
    if request.path == "/login":
        return
    if not session.get("logado"):
        return redirect("/login")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)