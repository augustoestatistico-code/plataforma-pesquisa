import os
import pandas as pd
from sqlalchemy import create_engine, text
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
server.secret_key = "chave_super_secreta_123"

# =========================
# LOGIN
# =========================
@app.server.route("/login", methods=["GET", "POST"])
def login():
    try:
        if request.method == "POST":
            email = request.form.get("email")
            senha = request.form.get("senha")

            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT * FROM usuarios 
                    WHERE email = :email AND senha = :senha
                """), {"email": email, "senha": senha}).fetchone()

            if result:
                session["usuario"] = email
                try:
                    session["pesquisa_id"] = result._mapping["pesquisa_id"]
                except:
                    session["pesquisa_id"] = 1

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

    except Exception as e:
        return f"Erro: {str(e)}"

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
# CARREGAR DADOS
# =========================
def carregar_dados():
    pesquisa_id = session.get("pesquisa_id")

    query = f"""
        SELECT *
        FROM entrevistas
        WHERE pesquisa_id = {pesquisa_id}
    """

    df = pd.read_sql(text(query), engine)

    # limpeza básica
    df = df.fillna("Não informado")

    return df

# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.Img(id="logo-cliente", style={"height": "80px"}),

    html.H1("📊 DASHBOARD ELEITORAL"),

    dcc.Dropdown(
        id="filtro-pergunta",
        placeholder="Escolha a pergunta",
        style={"width": "50%"}
    ),

    html.Br(),

    html.Div(id="kpis"),

    dcc.Graph(id="grafico-bairro"),

    html.H3("Entrevistadores"),
    html.Div(id="tabela-entrevistador"),

    html.H3("Análise por Pergunta"),
    dcc.Graph(id="grafico-dinamico"),

    html.Button("Exportar PDF", id="btn-pdf")
])

# =========================
# CALLBACK
# =========================
@app.callback(
    [
        Output("kpis", "children"),
        Output("grafico-bairro", "figure"),
        Output("tabela-entrevistador", "children"),
        Output("grafico-dinamico", "figure"),
        Output("filtro-pergunta", "options"),
        Output("logo-cliente", "src"),
    ],
    Input("filtro-pergunta", "value")
)
def atualizar(pergunta):

    df = carregar_dados()

    if df.empty:
        return "Sem dados", {}, "", {}, [], None

    total = len(df)

    # =========================
    # KPI
    # =========================
    kpis = html.Div([
        html.H3(f"Total Entrevistas: {total}")
    ])

    # =========================
    # BAIRRO
    # =========================
    bairro = df["localidade"].value_counts().reset_index()
    bairro.columns = ["bairro", "qtd"]

    fig_bairro = px.bar(
        bairro,
        x="qtd",
        y="bairro",
        orientation="h",
        title="Entrevistas por Bairro"
    )

    # =========================
    # ENTREVISTADOR
    # =========================
    ent = df["entrevistador"].value_counts().reset_index()
    ent.columns = ["Entrevistador", "Quantidade"]

    tabela = html.Table([
        html.Thead(html.Tr([
            html.Th("Entrevistador"),
            html.Th("Quantidade")
        ])),
        html.Tbody([
            html.Tr([
                html.Td(row["Entrevistador"]),
                html.Td(row["Quantidade"])
            ]) for _, row in ent.iterrows()
        ])
    ])

    # =========================
    # LISTA DE PERGUNTAS
    # =========================
    ignorar = ["id", "submission_id", "pesquisa_id", "dados"]
    colunas = [c for c in df.columns if c not in ignorar]

    opcoes = [{"label": c, "value": c} for c in colunas]

    # =========================
    # GRÁFICO DINÂMICO
    # =========================
    if not pergunta:
        pergunta = "SEXO" if "SEXO" in df.columns else colunas[0]

    graf = df[pergunta].value_counts().reset_index()
    graf.columns = ["categoria", "qtd"]

    fig_dinamico = px.bar(
        graf,
        x="qtd",
        y="categoria",
        orientation="h",
        title=f"Distribuição - {pergunta}"
    )

    # =========================
    # LOGO
    # =========================
    logo = None
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT logo FROM usuarios WHERE email = :email
        """), {"email": session.get("usuario")}).fetchone()

        if result:
            logo = result[0]

    return kpis, fig_bairro, tabela, fig_dinamico, opcoes, logo

# =========================
# PDF (simples)
# =========================
@app.callback(
    Output("btn-pdf", "children"),
    Input("btn-pdf", "n_clicks")
)
def exportar(n):
    if n:
        return "PDF gerado (implementar avançado depois)"
    return "Exportar PDF"

# =========================
# ETL
# =========================
@app.server.route("/etl")
def rodar_etl():
    token = request.args.get("token")

    if token != "123456":
        return "Acesso negado", 403

    os.system("python etl.py")
    return "ETL executado"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)