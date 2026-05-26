import os
import json
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

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# =========================
# LOGIN
# =========================
@server.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        query = text("""
            SELECT id, cliente_id
            FROM usuarios
            WHERE email = :email AND senha = :senha
        """)

        with engine.connect() as conn:
            user = conn.execute(query, {"email": email, "senha": senha}).fetchone()

        if user:
            session["user_id"] = user[0]
            session["cliente_id"] = user[1]
            return redirect("/dashboard/")

        return """
        <body style="background:#0f172a;color:white;font-family:Arial;text-align:center;margin-top:100px">
            <h2>Login inválido</h2>
            <a href="/" style="color:#38bdf8">Voltar</a>
        </body>
        """

    return """
    <body style="margin:0;background:#0f172a;font-family:Arial;color:white">
        <div style="width:360px;margin:120px auto;background:#111827;padding:35px;border-radius:18px;box-shadow:0 0 25px #000">
            <h2 style="text-align:center">📊 Plataforma Pesquisa</h2>
            <form method="post">
                <label>Email</label>
                <input name="email" style="width:100%;padding:12px;margin:8px 0 18px;border-radius:8px;border:0">
                <label>Senha</label>
                <input name="senha" type="password" style="width:100%;padding:12px;margin:8px 0 22px;border-radius:8px;border:0">
                <button style="width:100%;padding:13px;background:#2563eb;color:white;border:0;border-radius:10px;font-weight:bold">
                    Entrar
                </button>
            </form>
        </div>
    </body>
    """


@server.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@server.before_request
def proteger_dashboard():
    if request.path.startswith("/dashboard") and "cliente_id" not in session:
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
def get_cliente(cliente_id):
    query = text("""
        SELECT nome, logo
        FROM clientes
        WHERE id = :cliente_id
    """)

    with engine.connect() as conn:
        row = conn.execute(query, {"cliente_id": cliente_id}).fetchone()

    if row:
        return {"nome": row[0], "logo": row[1]}

    return {"nome": "Cliente", "logo": None}


def lista_pesquisas(cliente_id):
    df = pd.read_sql(
        text("""
            SELECT id, nome
            FROM pesquisas
            WHERE cliente_id = :cliente_id
            ORDER BY id DESC
        """),
        engine,
        params={"cliente_id": cliente_id}
    )

    return [{"label": row["nome"], "value": row["id"]} for _, row in df.iterrows()]


def carregar_dados(pesquisa_id):
    df = pd.read_sql(
        text("""
            SELECT id, submission_id, pesquisa_id, sexo, idade, localidade, dados, entrevistador
            FROM entrevistas
            WHERE pesquisa_id = :pesquisa_id
            ORDER BY id DESC
        """),
        engine,
        params={"pesquisa_id": pesquisa_id}
    )

    if df.empty:
        return df

    df["sexo"] = df["sexo"].fillna("Não informado").astype(str).str.strip().str.title()
    df["idade"] = df["idade"].fillna("Não informado").astype(str).str.strip()
    df["localidade"] = df["localidade"].fillna("Não informado").astype(str).str.strip().str.upper()
    df["entrevistador"] = df["entrevistador"].fillna("Não informado").astype(str).str.strip()

    return df


def normalizar_json(valor):
    if isinstance(valor, dict):
        return valor

    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except Exception:
            return {}

    return {}


def card(titulo, valor, subtitulo=""):
    return html.Div([
        html.Div(titulo, style={"fontSize": "13px", "color": "#94a3b8"}),
        html.Div(valor, style={"fontSize": "30px", "fontWeight": "bold", "marginTop": "6px"}),
        html.Div(subtitulo, style={"fontSize": "12px", "color": "#64748b", "marginTop": "4px"})
    ], style={
        "background": "#111827",
        "padding": "22px",
        "borderRadius": "18px",
        "boxShadow": "0 8px 25px rgba(0,0,0,.35)",
        "border": "1px solid #1f2937"
    })


def tema_fig(fig):
    fig.update_layout(
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        font_color="#e5e7eb",
        title_font_color="#ffffff",
        margin=dict(l=35, r=25, t=55, b=35),
        legend=dict(bgcolor="rgba(0,0,0,0)")
    )
    fig.update_xaxes(gridcolor="#1f2937")
    fig.update_yaxes(gridcolor="#1f2937")
    return fig


def pergunta_deve_ignorar(coluna):
    colunas_ignorar_fixas = {
        "meta.instanceID",
        "instanceID",
        "__system",
        "_id",
        "_uuid",
        "_submission_time",
        "nome",
        "loc1",
        "pesquisa_inicio",
        "pesquisa_fim",
        "hoje",
        "HOJE",
        "PESQUISA_INICIO",
        "PESQUISA_FIM"
    }

    if coluna in colunas_ignorar_fixas:
        return True

    if coluna.startswith("_system."):
        return True

    if coluna.startswith("_"):
        return True

    return False


def gerar_graficos_perguntas(df, pesquisa_id):
    perguntas = []

    if "dados" not in df.columns:
        return perguntas

    dados_normalizados = df["dados"].apply(normalizar_json)
    json_df = pd.json_normalize(dados_normalizados)

    if json_df.empty:
        return perguntas

    for coluna in json_df.columns:
        if pergunta_deve_ignorar(coluna):
            continue

        serie = json_df[coluna].dropna().astype(str).str.strip()
        serie = serie[serie != ""]

        if serie.empty:
            continue

        contagem = serie.value_counts().reset_index()
        contagem.columns = ["Resposta", "Quantidade"]
        contagem["%"] = (contagem["Quantidade"] / contagem["Quantidade"].sum() * 100).round(1)
        contagem["Texto"] = (
            contagem["Quantidade"].astype(str)
            + " ("
            + contagem["%"].astype(str)
            + "%)"
        )

        if len(contagem) > 15:
            contagem = contagem.head(15)

label = coluna

try:

    df_label = pd.read_sql(
        text("""
        SELECT label
        FROM perguntas_pesquisa
        WHERE pesquisa_id=:pesquisa_id
        AND UPPER(name)=:name
        LIMIT 1
        """),
        engine,
        params={
            "pesquisa_id": pesquisa_id,
            "name": coluna.upper()
        }
    )

    if not df_label.empty:
        label = df_label.iloc[0]["label"]

except:
    pass


fig = px.bar(
    contagem.sort_values("Quantidade", ascending=True),
    x="Quantidade",
    y="Resposta",
    orientation="h",
    text="Texto",
    title=label
)

        fig = tema_fig(fig)

        perguntas.append(
            html.Div([
                dcc.Graph(figure=fig)
            ], style={
                "background": "#111827",
                "borderRadius": "18px",
                "border": "1px solid #1f2937",
                "marginBottom": "18px",
                "padding": "10px"
            })
        )

    return perguntas


# =========================
# LAYOUT
# =========================
app.layout = html.Div([
    dcc.Location(id="url"),

    html.Div([
        html.Div([
            html.H2("📊 Dashboard Pesquisa", style={"margin": "0"}),
            html.Div(id="cliente-header", style={"color": "#94a3b8", "marginTop": "6px"}),
        ]),

        html.Div([
            html.A("Sair", href="/logout", style={
                "color": "white",
                "background": "#dc2626",
                "padding": "10px 18px",
                "borderRadius": "10px",
                "textDecoration": "none"
            })
        ])
    ], style={
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
        "padding": "22px 28px",
        "background": "#020617",
        "borderBottom": "1px solid #1f2937"
    }),

    html.Div([
        html.Label("Selecione a pesquisa", style={"fontWeight": "bold"}),
        dcc.Dropdown(
            id="pesquisa",
            options=[],
            value=None,
            placeholder="Escolha uma pesquisa",
            style={"color": "#111827", "marginTop": "8px"}
        )
    ], style={"padding": "22px 28px"}),

    html.Div(id="kpis", style={
        "display": "grid",
        "gridTemplateColumns": "repeat(4, 1fr)",
        "gap": "18px",
        "padding": "0 28px 22px"
    }),

    html.Div([
        dcc.Graph(id="grafico-sexo"),
        dcc.Graph(id="grafico-idade"),
    ], style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "18px",
        "padding": "0 28px 22px"
    }),

    html.Div([
        dcc.Graph(id="grafico-localidade"),
    ], style={"padding": "0 28px 22px"}),

    html.Div([
        html.Div([
            html.H3("Produção por Entrevistador"),
            html.Div(id="tabela-entrevistador")
        ], style={
            "background": "#111827",
            "padding": "20px",
            "borderRadius": "18px",
            "border": "1px solid #1f2937"
        })
    ], style={"padding": "0 28px 22px"}),

    html.Div([
        html.H2("Resultados das Perguntas", style={"marginBottom": "16px"}),
        html.Div(id="perguntas-dinamicas")
    ], style={"padding": "0 28px 40px"}),

], style={
    "background": "#0f172a",
    "minHeight": "100vh",
    "color": "#e5e7eb",
    "fontFamily": "Arial, sans-serif"
})


# =========================
# CALLBACK PESQUISAS
# =========================
@app.callback(
    [
        Output("pesquisa", "options"),
        Output("pesquisa", "value"),
        Output("cliente-header", "children"),
    ],
    Input("url", "pathname")
)
def inicializar_dashboard(pathname):
    cliente_id = session.get("cliente_id")

    if not cliente_id:
        return [], None, ""

    cliente = get_cliente(cliente_id)
    options = lista_pesquisas(cliente_id)
    valor_inicial = options[0]["value"] if options else None

    logo = cliente.get("logo")
    header = html.Div([
        html.Img(
            src=logo,
            style={
                "height": "45px",
                "marginRight": "12px",
                "borderRadius": "8px",
                "objectFit": "contain",
                "background": "white"
            }
        ) if logo else None,

        html.Div([
            html.Div(f"Cliente: {cliente['nome']}", style={"fontWeight": "bold"}),
            html.Div(
                "Dashboard de pesquisas em andamento",
                style={"fontSize": "12px", "color": "#94a3b8"}
            )
        ])
    ], style={
        "display": "flex",
        "alignItems": "center",
        "gap": "10px"
    })

    return options, valor_inicial, header


# =========================
# CALLBACK DASHBOARD
# =========================
@app.callback(
    [
        Output("kpis", "children"),
        Output("grafico-sexo", "figure"),
        Output("grafico-idade", "figure"),
        Output("grafico-localidade", "figure"),
        Output("tabela-entrevistador", "children"),
        Output("perguntas-dinamicas", "children"),
    ],
    Input("pesquisa", "value")
)
def atualizar_dashboard(pesquisa_id):

    if not pesquisa_id:
        fig_vazio = tema_fig(px.bar(title="Sem pesquisa selecionada"))
        return [], fig_vazio, fig_vazio, fig_vazio, "", ""

    df = carregar_dados(pesquisa_id)

    if df.empty:
        fig_vazio = tema_fig(px.bar(title="Sem dados"))
        return [
            card("Total", "0", "Sem entrevistas")
        ], fig_vazio, fig_vazio, fig_vazio, "Sem dados", ""

    total = len(df)
    localidades = df["localidade"].nunique()
    entrevistadores = df["entrevistador"].nunique()

    masc = int((df["sexo"] == "Masculino").sum())
    fem = int((df["sexo"] == "Feminino").sum())

    masc_pct = round((masc / total) * 100, 1) if total else 0
    fem_pct = round((fem / total) * 100, 1) if total else 0

    kpis = [
        card("Total de Entrevistas", f"{total:,}".replace(",", "."), "Amostra realizada"),
        card("Masculino", f"{masc_pct}%", f"{masc} entrevistas"),
        card("Feminino", f"{fem_pct}%", f"{fem} entrevistas"),
        card("Localidades", localidades, f"{entrevistadores} entrevistadores"),
    ]

    sexo_df = df["sexo"].value_counts().reset_index()
    sexo_df.columns = ["Sexo", "Quantidade"]
    fig_sexo = px.pie(
        sexo_df,
        names="Sexo",
        values="Quantidade",
        title="Distribuição por Sexo",
        hole=0.45
    )
    fig_sexo = tema_fig(fig_sexo)

    idade_ordem = [
        "16 a 24 anos",
        "25 a 34 anos",
        "35 a 44 anos",
        "45 a 59 anos",
        "60 anos ou mais",
        "Não informado"
    ]

    idade_df = df["idade"].value_counts().reset_index()
    idade_df.columns = ["Faixa Etária", "Quantidade"]
    idade_df["Faixa Etária"] = pd.Categorical(
        idade_df["Faixa Etária"],
        categories=idade_ordem,
        ordered=True
    )
    idade_df = idade_df.sort_values("Faixa Etária")

    fig_idade = px.bar(
        idade_df,
        x="Faixa Etária",
        y="Quantidade",
        text="Quantidade",
        title="Distribuição por Faixa Etária"
    )
    fig_idade = tema_fig(fig_idade)

    loc_df = df["localidade"].value_counts().reset_index()
    loc_df.columns = ["Localidade", "Quantidade"]
    loc_df["%"] = (loc_df["Quantidade"] / total * 100).round(1)
    loc_df["Texto"] = (
        loc_df["Quantidade"].astype(str)
        + " ("
        + loc_df["%"].astype(str)
        + "%)"
    )
    loc_df = loc_df.sort_values("Quantidade", ascending=True)

    fig_localidade = px.bar(
        loc_df,
        x="Quantidade",
        y="Localidade",
        orientation="h",
        text="Texto",
        title="Entrevistas por Localidade"
    )
    fig_localidade = tema_fig(fig_localidade)

    ent_df = df["entrevistador"].value_counts().reset_index()
    ent_df.columns = ["Entrevistador", "Quantidade"]
    ent_df["%"] = (ent_df["Quantidade"] / total * 100).round(1)

    tabela_ent = dash_table.DataTable(
        data=ent_df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in ent_df.columns],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#020617",
            "color": "white",
            "fontWeight": "bold",
            "border": "1px solid #1f2937"
        },
        style_cell={
            "backgroundColor": "#111827",
            "color": "#e5e7eb",
            "border": "1px solid #1f2937",
            "padding": "10px",
            "textAlign": "left"
        },
        page_size=10
    )

    perguntas = gerar_graficos_perguntas(df)

    if not perguntas:
        perguntas = [
            html.Div("Nenhuma pergunta encontrada no campo dados JSONB.", style={
                "background": "#111827",
                "padding": "20px",
                "borderRadius": "18px"
            })
        ]

    return (
        kpis,
        fig_sexo,
        fig_idade,
        fig_localidade,
        tabela_ent,
        perguntas
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
