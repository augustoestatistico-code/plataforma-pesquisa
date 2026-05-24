import os
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.express as px
from flask import Flask, request, session, redirect

# =========================
# CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")

server = Flask(__name__)
server.secret_key = SECRET_KEY

engine = create_engine(DATABASE_URL)

# =========================
# LOGIN
# =========================
@server.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = text("""
            SELECT u.id, u.cliente_id, c.nome, c.logo
            FROM usuarios u
            LEFT JOIN clientes c ON c.id = u.cliente_id
            WHERE u.email = :email AND u.senha = :senha
        """)

        with engine.connect() as conn:
            user = conn.execute(query, {"email": email, "senha": senha}).fetchone()

        if user:
            session["user_id"] = user[0]
            session["cliente_id"] = user[1]
            session["cliente_nome"] = user[2]
            session["cliente_logo"] = user[3]
            return redirect("/dashboard/")

        return "<h3>Login inválido</h3><a href='/'>Voltar</a>"

    return """
    <html>
    <head>
        <title>Login Dashboard</title>
        <style>
            body {
                font-family: Arial;
                background: #0f172a;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                color: white;
            }
            .box {
                background: #111827;
                padding: 40px;
                border-radius: 18px;
                width: 360px;
                box-shadow: 0 10px 40px rgba(0,0,0,.4);
            }
            input {
                width: 100%;
                padding: 12px;
                margin: 8px 0 18px 0;
                border-radius: 8px;
                border: none;
            }
            button {
                width: 100%;
                padding: 14px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>📊 Dashboard de Pesquisas</h2>
            <form method="post">
                <label>Email</label>
                <input name="email" type="email" required>
                <label>Senha</label>
                <input name="senha" type="password" required>
                <button type="submit">Entrar</button>
            </form>
        </div>
    </body>
    </html>
    """

@server.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =========================
# PROTEGER DASHBOARD
# =========================
@server.before_request
def proteger():
    if request.path.startswith("/dashboard"):
        if "cliente_id" not in session:
            return redirect("/")

# =========================
# DASH
# =========================
app = dash.Dash(
    __name__,
    server=server,
    url_base_pathname="/dashboard/",
    suppress_callback_exceptions=True
)

# =========================
# FUNÇÕES
# =========================
def lista_pesquisas(cliente_id):
    df = pd.read_sql(text("""
        SELECT id, nome
        FROM pesquisas
        WHERE cliente_id = :cliente_id
        ORDER BY id DESC
    """), engine, params={"cliente_id": cliente_id})

    return [{"label": row["nome"], "value": row["id"]} for _, row in df.iterrows()]


def carregar_dados(pesquisa_id):

    print("PESQUISA RECEBIDA:", pesquisa_id)

    query = text("""
        SELECT
            pesquisa_id,
            sexo,
            idade,
            localidade,
            entrevistador,
            dados
        FROM entrevistas
        WHERE pesquisa_id=:pesquisa_id
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "pesquisa_id": int(pesquisa_id)
        }
    )

    print("TOTAL LINHAS:",len(df))

    if not df.empty:
        print(df.head())

    return df

def tabela_freq(df, coluna):
    base = df[coluna].value_counts(dropna=False).reset_index()
    base.columns = [coluna, "Quantidade"]
    base["Percentual"] = (base["Quantidade"] / base["Quantidade"].sum() * 100).round(1)
    base["Percentual"] = base["Percentual"].astype(str) + "%"
    return base


def card(titulo, valor, subtitulo=""):
    return html.Div([
        html.Div(titulo, className="card-title"),
        html.Div(valor, className="card-value"),
        html.Div(subtitulo, className="card-subtitle")
    ], className="card")


def gerar_tabela(df):
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={
            "backgroundColor": "#111827",
            "color": "white",
            "border": "1px solid #374151",
            "padding": "8px",
            "fontSize": "13px"
        },
        style_header={
            "backgroundColor": "#1f2937",
            "fontWeight": "bold"
        }
    )


def limpar_chave(chave):
    excluir = [
        "id", "uuid", "submission", "submission_id", "instance",
        "data", "date", "datetime", "start", "end",
        "today", "device", "meta", "formhub",
        "codigo", "cod", "gps", "latitude", "longitude",
        "_id", "_uuid", "_submission_time", "_index"
    ]

    chave_min = str(chave).lower()

    for termo in excluir:
        if termo in chave_min:
            return False

    return True


def extrair_gps(df):
    pontos = []

    if "dados" not in df.columns:
        return pd.DataFrame()

    for _, row in df.iterrows():
        dados = row["dados"]

        if not isinstance(dados, dict):
            continue

        lat = None
        lon = None

        for k, v in dados.items():
            kmin = str(k).lower()

            if kmin in ["latitude", "lat", "gps_latitude"]:
                lat = v

            if kmin in ["longitude", "lon", "lng", "gps_longitude"]:
                lon = v

            if "gps" in kmin and isinstance(v, str):
                partes = v.replace(",", " ").split()
                if len(partes) >= 2:
                    try:
                        lat = float(partes[0])
                        lon = float(partes[1])
                    except:
                        pass

        try:
            if lat is not None and lon is not None:
                pontos.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "localidade": row.get("localidade", ""),
                    "entrevistador": row.get("entrevistador", "")
                })
        except:
            pass

    return pd.DataFrame(pontos)


# =========================
# LAYOUT
# =========================
app.layout = html.Div([

    html.Div([
        html.Div([
            html.H2("📊 Painel de Pesquisas"),
            html.Div(id="cliente-info"),
            html.A("Sair", href="/logout", className="logout")
        ], className="sidebar"),

        html.Div([

            html.Div([
                html.H1("Dashboard Gerencial"),
                dcc.Dropdown(
                    id="pesquisa",
                    placeholder="Selecione uma pesquisa",
                    className="dropdown"
                )
            ], className="topbar"),

            html.Div(id="kpis", className="kpi-grid"),

            html.Div([
                html.Div([dcc.Graph(id="grafico-sexo")], className="panel"),
                html.Div([dcc.Graph(id="grafico-idade")], className="panel"),
            ], className="grid-2"),

            html.Div([
                html.Div([dcc.Graph(id="grafico-localidade")], className="panel"),
            ], className="grid-1"),

            html.Div([
                html.H3("Perfil da Amostra"),
                html.Div(id="tabelas-perfil")
            ], className="panel"),

            html.Div([
                html.H3("Mapa por GPS"),
                dcc.Graph(id="mapa-gps")
            ], className="panel"),

            html.Div([
                html.H3("Resultados das Questões da Pesquisa"),
                html.Div(id="questoes")
            ], className="panel"),

        ], className="main")
    ], className="layout")
])


app.index_string = """
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>Dashboard Pesquisa</title>
    {%favicon%}
    {%css%}
    <style>
        body {
            margin: 0;
            background: #020617;
            color: white;
            font-family: Arial, sans-serif;
        }
        .layout {
            display: flex;
            min-height: 100vh;
        }
        .sidebar {
            width: 250px;
            background: #0f172a;
            padding: 28px 22px;
            border-right: 1px solid #1e293b;
        }
        .sidebar h2 {
            font-size: 22px;
            margin-bottom: 30px;
        }
        .logout {
            display: inline-block;
            margin-top: 30px;
            color: #93c5fd;
            text-decoration: none;
        }
        .main {
            flex: 1;
            padding: 28px;
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
            margin-bottom: 24px;
        }
        .topbar h1 {
            margin: 0;
            font-size: 30px;
        }
        .dropdown {
            width: 360px;
            color: #111827;
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 18px;
            margin-bottom: 20px;
        }
        .card {
            background: linear-gradient(135deg, #1e293b, #111827);
            border: 1px solid #334155;
            padding: 22px;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,.25);
        }
        .card-title {
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 8px;
        }
        .card-value {
            font-size: 30px;
            font-weight: bold;
        }
        .card-subtitle {
            color: #cbd5e1;
            font-size: 12px;
            margin-top: 6px;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin-bottom: 18px;
        }
        .grid-1 {
            display: grid;
            grid-template-columns: 1fr;
            gap: 18px;
            margin-bottom: 18px;
        }
        .panel {
            background: #0f172a;
            border: 1px solid #1e293b;
            padding: 20px;
            border-radius: 18px;
            margin-bottom: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,.22);
        }
        .questao-card {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 14px;
            padding: 16px;
            margin-bottom: 18px;
        }
        @media(max-width: 900px) {
            .layout {
                flex-direction: column;
            }
            .sidebar {
                width: auto;
            }
            .topbar {
                flex-direction: column;
                align-items: stretch;
            }
            .dropdown {
                width: 100%;
            }
            .kpi-grid, .grid-2 {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
"""

# =========================
# CALLBACK
# =========================
@app.callback(
    [
        Output("pesquisa", "options"),
        Output("pesquisa", "value"),
        Output("cliente-info", "children"),
        Output("kpis", "children"),
        Output("grafico-sexo", "figure"),
        Output("grafico-idade", "figure"),
        Output("grafico-localidade", "figure"),
        Output("tabelas-perfil", "children"),
        Output("mapa-gps", "figure"),
        Output("questoes", "children"),
    ],
    Input("pesquisa", "value")
)
def atualizar(pesquisa_id):

    cliente_id = session.get("cliente_id")
    cliente_nome = session.get("cliente_nome", "Cliente")

    options = lista_pesquisas(cliente_id)

    if options and pesquisa_id is None:
        pesquisa_id = options[0]["value"]

    print("CLIENTE:", cliente_id)
    print("PESQUISAS:", options)
    

    if not pesquisa_id and options:
        pesquisa_id = options[0]["value"]

    cliente_info = html.Div([
        html.Div(cliente_nome),
        html.Small(f"Cliente ID: {cliente_id}")
    ])

    vazio = px.scatter(title="Sem dados")

    if not options:
        return [], None, cliente_info, [card("Pesquisas", "0")], vazio, vazio, vazio, "", vazio, ""

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return options, pesquisa_id, cliente_info, [card("Total da Amostra", "0")], vazio, vazio, vazio, "", vazio, ""

    total = len(df)

    qtd_localidades = df["localidade"].nunique()
    qtd_entrevistadores = df["entrevistador"].nunique()

    sexo_tab = tabela_freq(df, "sexo")
    idade_tab = tabela_freq(df, "idade")
    local_tab = tabela_freq(df, "localidade")
    ent_tab = tabela_freq(df, "entrevistador")

    kpis = [
        card("Total da Amostra", f"{total:,}".replace(",", ".")),
        card("Localidades", qtd_localidades),
        card("Entrevistadores", qtd_entrevistadores),
        card("Pesquisa ID", pesquisa_id),
    ]

    fig_sexo = px.pie(
        sexo_tab,
        names="sexo",
        values="Quantidade",
        title="Distribuição por Sexo",
        hole=0.45
    )

    fig_idade = px.bar(
        idade_tab,
        x="idade",
        y="Quantidade",
        text="Percentual",
        title="Distribuição por Faixa Etária"
    )

    fig_local = px.bar(
        local_tab.sort_values("Quantidade", ascending=True),
        x="Quantidade",
        y="localidade",
        orientation="h",
        text="Percentual",
        title="Quantidade e Percentual por Localidade"
    )

    for fig in [fig_sexo, fig_idade, fig_local]:
        fig.update_layout(
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            font_color="white",
            margin=dict(l=20, r=20, t=60, b=20)
        )

    tabelas = html.Div([
        html.H4("Sexo"),
        gerar_tabela(sexo_tab),

        html.Br(),
        html.H4("Faixa Etária"),
        gerar_tabela(idade_tab),

        html.Br(),
        html.H4("Localidade"),
        gerar_tabela(local_tab),

        html.Br(),
        html.H4("Entrevistador"),
        gerar_tabela(ent_tab),
    ])

    # =========================
    # MAPA GPS
    # =========================
    gps = extrair_gps(df)

    if not gps.empty:
        fig_mapa = px.scatter_mapbox(
            gps,
            lat="lat",
            lon="lon",
            hover_name="localidade",
            hover_data=["entrevistador"],
            zoom=11,
            height=500,
            title="Localização das Entrevistas"
        )
        fig_mapa.update_layout(
            mapbox_style="open-street-map",
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            font_color="white",
            margin=dict(l=0, r=0, t=50, b=0)
        )
    else:
        fig_mapa = px.scatter(title="Sem GPS disponível nesta pesquisa")
        fig_mapa.update_layout(
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            font_color="white"
        )
    # =========================
    # QUESTÕES DINÂMICAS
    # =========================

    questoes=[]

    # CARREGA LABELS DA PESQUISA
    labels_perguntas, tipos_perguntas, ordem_perguntas = carregar_labels(pesquisa_id)

    respostas=df["dados"].dropna()

    todas_chaves=set()

    for item in respostas:
        if isinstance(item,dict):
            todas_chaves.update(item.keys())

    chaves_validas = [
        c for c in ordem_perguntas
        if c in todas_chaves and limpar_chave(c)
    ]

    for chave in chaves_validas:

        valores=[]

        for item in respostas:

            if isinstance(item,dict):

                valor=item.get(chave)

                if valor not in [None,"","nan"]:
                    valores.append(str(valor).strip())

        if not valores:
            continue

        contagem=pd.Series(valores).value_counts().reset_index()

        if len(contagem)>30:
            continue

        contagem.columns=["Resposta","Quantidade"]

        contagem["Percentual"]=(
            contagem["Quantidade"] /
            contagem["Quantidade"].sum()*100
        ).round(1)

        contagem["Texto"]=(
            contagem["Quantidade"].astype(str)
            +" ("+
            contagem["Percentual"].astype(str)
            +"%)"
        )

        fig=px.bar(
            contagem.sort_values("Quantidade",ascending=True),
            x="Quantidade",
            y="Resposta",
            orientation="h",
            text="Texto",
            title=labels_perguntas.get(chave,chave)
        )

        fig.update_layout(
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            font_color="white"
        )

        questoes.append(
            html.Div([
                dcc.Graph(figure=fig),
                gerar_tabela(contagem)
            ],className="questao-card")
        )

    if not questoes:
        questoes = html.Div(
            "Nenhuma questão encontrada"
        )

    return (
        options,
        pesquisa_id,
        cliente_info,
        kpis,
        fig_sexo,
        fig_idade,
        fig_local,
        tabelas,
        fig_mapa,
        questoes
    )
# =========================
# ETL ENDPOINT
# =========================
@server.route("/etl")
def rodar_etl():
    token = request.args.get("token")

    if token != "123456":
        return "Acesso negado", 403

    os.system("python etl.py")
    return "ETL executado com sucesso"


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)