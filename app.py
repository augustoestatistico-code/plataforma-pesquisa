import os
import json
import pandas as pd
from sqlalchemy import create_engine, text
import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.express as px
from flask import Flask, request, session, redirect, Response
import subprocess
import sys
import requests
from requests.auth import HTTPBasicAuth
import urllib.parse

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io

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
        SELECT nome, logo_url
        FROM clientes
        WHERE id = :cliente_id
    """)

    with engine.connect() as conn:
        row = conn.execute(query, {"cliente_id": cliente_id}).fetchone()

    if row:
        logo = row[1] or "/dashboard/assets/logos/sem_logo.png"
        return {"nome": row[0], "logo": logo}

    return {
        "nome": "Cliente",
        "logo": "/dashboard/assets/logos/sem_logo.png"
    }


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


def extrair_gps(df):
    pontos = []

    if "dados" not in df.columns:
        return pd.DataFrame()

    for _, row in df.iterrows():
        dados = normalizar_json(row.get("dados"))

        lat = dados.get("latitude_melhor") or dados.get("lat_final") or dados.get("lat_inicio")
        lon = dados.get("longitude_melhor") or dados.get("lon_final") or dados.get("lon_inicio")

        if (not lat or not lon) and isinstance(dados.get("gps_final"), dict):
            coords = dados["gps_final"].get("coordinates", [])
            if len(coords) >= 2:
                lon = coords[0]
                lat = coords[1]

        try:
            if lat and lon:
                pontos.append({
                    "submission_id": row.get("submission_id"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "localidade": row.get("localidade", ""),
                    "entrevistador": row.get("entrevistador", ""),
                    "accuracy": dados.get("accuracy_melhor") or dados.get("acc_final") or ""
                })
        except:
            pass

    return pd.DataFrame(pontos)


def card(titulo, valor, subtitulo="", cor="#2563eb"):
    return html.Div([
        html.Div(titulo.upper(), style={
            "fontSize": "12px",
            "fontWeight": "bold",
            "color": "#bfdbfe"
        }),
        html.Div(valor, style={
            "fontSize": "34px",
            "fontWeight": "bold",
            "marginTop": "8px",
            "color": "white"
        }),
        html.Div(subtitulo, style={
            "fontSize": "12px",
            "color": "#cbd5e1",
            "marginTop": "6px"
        })
    ], style={
        "background": f"linear-gradient(135deg, {cor}, #0f172a)",
        "padding": "22px",
        "borderRadius": "16px",
        "border": "1px solid #1e293b",
        "boxShadow": "0 8px 24px rgba(0,0,0,.35)"
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

def cor_resposta_mapa(valor):

    valor = str(valor).strip().lower()

    mapa = {
        "aprova": "#16a34a",
        "desaprova": "#dc2626",
        "ótima": "#15803d",
        "otima": "#15803d",
        "boa": "#22c55e",
        "regular": "#facc15",
        "ruim": "#f97316",
        "péssima": "#b91c1c",
        "pessima": "#b91c1c",
        "sim": "#16a34a",
        "não": "#dc2626",
        "nao": "#dc2626",
        "talvez": "#facc15",
        "indeciso": "#9ca3af",
        "indeciso ": "#9ca3af",
        "não sabe": "#9ca3af",
        "nao sabe": "#9ca3af",
        "ns/nr": "#9ca3af",
        "nenhum": "#6b7280",
        "branco/nulo": "#6b7280",
    }

    return mapa.get(valor, "#3b82f6")

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

def gerar_graficos_perguntas(df, pesquisa_id, pergunta_selecionada=None):
    perguntas = []

    if "dados" not in df.columns:
        return perguntas

    dados_normalizados = df["dados"].apply(normalizar_json)
    json_df = pd.json_normalize(dados_normalizados)

    if json_df.empty:
        return perguntas

    perguntas_exibir = pd.read_sql(
        text("""
            SELECT
                UPPER(name) AS name,
                label,
                id
            FROM perguntas_pesquisa
            WHERE pesquisa_id = :pesquisa_id
            AND exibir_dashboard = true
            ORDER BY id
        """),
        engine,
        params={"pesquisa_id": pesquisa_id}
    )

    lista_exibir = set(perguntas_exibir["name"].tolist())
    labels = dict(zip(perguntas_exibir["name"], perguntas_exibir["label"]))

    if pergunta_selecionada:
        ordem_perguntas = [pergunta_selecionada.upper()]
    else:
        ordem_perguntas = perguntas_exibir["name"].tolist()

    for coluna_upper in ordem_perguntas:

        coluna_real = None

        for c in json_df.columns:
            if c.upper() == coluna_upper:
                coluna_real = c
                break

        if coluna_real is None:
            continue

        coluna = coluna_real
        coluna_upper = coluna.upper()

        if coluna_upper not in lista_exibir:
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

        titulo = labels.get(coluna_upper, coluna)

        fig = px.bar(
            contagem.sort_values("Quantidade", ascending=True),
            x="Quantidade",
            y="Resposta",
            orientation="h",
            text="Texto",
            title=titulo
        )

        fig = tema_fig(fig)

        tabela_respostas = dash_table.DataTable(
            data=contagem.to_dict("records"),
            columns=[
                {"name": "Resposta", "id": "Resposta"},
                {"name": "Quantidade", "id": "Quantidade"},
                {"name": "%", "id": "%"},
            ],
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
                "padding": "8px",
                "textAlign": "left"
            },
            page_size=15
        )

        perguntas.append(
            html.Div([
                dcc.Graph(figure=fig),
                html.H4("Tabela de respostas", style={"marginTop": "10px"}),
                tabela_respostas
            ], style={
                "background": "#111827",
                "borderRadius": "18px",
                "border": "1px solid #1f2937",
                "marginBottom": "18px",
                "padding": "14px"
            })
        )

    return perguntas

# =========================
# ÁUDIOS
# =========================
def carregar_audios(pesquisa_id):

    try:
        sql = """
            SELECT
                pesquisa_id,
                submission_id,
                entrevistador,
                localidade,
                data_entrevista,
                nome_arquivo
            FROM audios_entrevistas
            WHERE pesquisa_id = %(pesquisa_id)s
            ORDER BY id DESC
            LIMIT 100
        """

        df = pd.read_sql(sql, engine, params={"pesquisa_id": pesquisa_id})

        if df.empty:
            return html.Div("Nenhum áudio disponível nesta pesquisa.", style={"color": "#9ca3af"})

        linhas = []

        for _, row in df.iterrows():
            audio_src = f"/audio/{row['pesquisa_id']}/{row['submission_id']}/{row['nome_arquivo']}"

            linhas.append(html.Tr([
                html.Td(row["entrevistador"]),
                html.Td(row["localidade"]),
                html.Td(str(row["data_entrevista"])),
                html.Td( html.Audio(
                            src=audio_src,
                            controls=True,
                            style={"width": "300px"}
                        ))
            ]))

        return html.Table([
            html.Thead(html.Tr([
                html.Th("Entrevistador"),
                html.Th("Localidade"),
                html.Th("Data"),
                html.Th("Áudio")
            ])),
            html.Tbody(linhas)
        ], style={"width": "100%", "color": "white"})

    except Exception as e:
        return html.Div(f"Erro ao carregar áudios: {e}")
    
# =========================
# LAYOUT
# =========================

# =========================
# LAYOUT POWER BI
# =========================
app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="secao-ativa", data="visao-geral"),

    # SIDEBAR
    html.Div([
        html.H2([
            html.Span("Ipsensus", style={"color": "#1e88ff"}),
            html.Span(" Survey", style={"color": "white"})
        ], style={"margin": "0", "fontSize": "24px"}),

        html.Div("MENU", style={
            "color": "#94a3b8",
            "fontSize": "13px",
            "marginTop": "30px",
            "marginBottom": "12px"
        }),

        html.Button("📊 Visão Geral", id="btn-visao-geral", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "background": "#2563eb", "padding": "12px",
            "borderRadius": "8px", "marginBottom": "10px",
            "fontWeight": "bold", "color": "white",
            "border": "0", "cursor": "pointer"
        }),

        html.Button("📝 Entrevistas", id="btn-entrevistas", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),

        html.Button("🗺️ Mapas", id="btn-mapas", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),

        html.Button("📋 Perguntas", id="btn-perguntas", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),

        html.Button("👥 Entrevistadores", id="btn-entrevistadores", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),

        html.Button("📄 Relatórios", id="btn-relatorios", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),
        html.Button("🧠 Inteligência", id="btn-inteligencia", n_clicks=0, style={
            "display": "block", "width": "100%", "textAlign": "left",
            "padding": "10px", "color": "#cbd5e1",
            "background": "transparent", "border": "0", "cursor": "pointer"
        }),
        
        html.Hr(style={"borderColor": "#1f2937", "marginTop": "25px"}),

        html.Div("FILTROS", style={
            "color": "#94a3b8",
            "fontSize": "13px",
            "marginBottom": "12px"
        }),

        html.Label("Pesquisa", style={"fontSize": "13px"}),
        dcc.Dropdown(
            id="pesquisa",
            options=[],
            value=None,
            placeholder="Selecione",
            style={"color": "#111827", "marginTop": "6px", "marginBottom": "16px"}
        ),

        html.Label("Localidade", style={"fontSize": "13px"}),
        dcc.Dropdown(
            id="filtro-localidade",
            options=[],
            value=None,
            placeholder="Todas",
            style={"color": "#111827", "marginTop": "6px", "marginBottom": "16px"}
        ),

        html.Label("Entrevistador", style={"fontSize": "13px"}),
        dcc.Dropdown(
            id="filtro-entrevistador",
            options=[],
            value=None,
            placeholder="Todos",
            style={"color": "#111827", "marginTop": "6px", "marginBottom": "16px"}
        ),

        html.Label("Pergunta para análise", style={"fontSize": "13px"}),
        dcc.Dropdown(
            id="pergunta-mapa",
            options=[],
            value=None,
            placeholder="Selecione uma pergunta",
            style={"color": "#111827", "marginTop": "6px", "marginBottom": "16px"}
        ),

        html.Label("Tipo de Mapa", style={"fontSize": "13px"}),
        dcc.Dropdown(
            id="tipo-mapa",
            options=[
                {"label": "Mapa de Pontos", "value": "pontos"},
                {"label": "Mapa de Calor", "value": "calor"},
            ],
            value="pontos",
            clearable=False,
            style={"color": "#111827", "marginTop": "6px", "marginBottom": "16px"}
        ),

        html.A("Sair", href="/logout", style={
            "display": "block",
            "marginTop": "25px",
            "color": "white",
            "background": "#dc2626",
            "padding": "10px",
            "borderRadius": "8px",
            "textAlign": "center",
            "textDecoration": "none"
        }),

    ], style={
        "position": "fixed",
        "left": "0",
        "top": "0",
        "bottom": "0",
        "width": "260px",
        "background": "#020617",
        "padding": "24px 16px",
        "borderRight": "1px solid #1f2937",
        "color": "white",
        "overflowY": "auto"
    }),

    # CONTEÚDO PRINCIPAL
        html.Div([

            html.Div([
                html.Div([
                    html.H2("Acompanhamento em Tempo Real", style={"margin": "0"}),
                    html.Div("Dados atualizados automaticamente", style={
                        "color": "#94a3b8",
                        "fontSize": "13px",
                        "marginTop": "4px"
                    }),
                ]),

                html.Div([
                    html.Div(id="cliente-header", style={"color": "#cbd5e1"}),
                    html.Div(id="pesquisa-header", style={
                        "color": "#94a3b8",
                        "fontSize": "12px",
                        "marginTop": "6px",
                        "textAlign": "right"
                    })
                ])
            ], style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "marginBottom": "22px"
            }),

        html.Div([
            html.Div(id="kpis", style={
                "display": "grid",
                "gridTemplateColumns": "repeat(4, 1fr)",
                "gap": "18px",
                "marginBottom": "20px"
            }),

            html.Div([
                html.Div([dcc.Graph(id="grafico-sexo")], style={
                    "background": "#111827",
                    "borderRadius": "14px",
                    "border": "1px solid #1f2937",
                    "padding": "10px"
                }),
                html.Div([dcc.Graph(id="grafico-idade")], style={
                    "background": "#111827",
                    "borderRadius": "14px",
                    "border": "1px solid #1f2937",
                    "padding": "10px"
                }),
            ], style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gap": "18px",
                "marginBottom": "20px"
            }),
        ], id="secao-visao-geral"),

        html.Div([
            html.Div([dcc.Graph(id="mapa-gps")], style={
                "background": "#111827",
                "borderRadius": "14px",
                "border": "1px solid #1f2937",
                "padding": "10px"
            }),
        ], id="secao-mapas"),

        html.Div([
            html.H2("Resultados das Perguntas", style={"marginBottom": "16px"}),
            html.Div(id="perguntas-dinamicas")
        ], id="secao-perguntas"),

        html.Div([
            html.H3("Desempenho por Entrevistador", style={"marginTop": "0"}),
            html.Div(id="tabela-entrevistador")
        ], id="secao-entrevistadores", style={
            "background": "#111827",
            "borderRadius": "14px",
            "border": "1px solid #1f2937",
            "padding": "18px"
        }),

        html.Div([
            html.H2("Entrevistas / Auditoria", style={
                "marginTop": "0",
                "marginBottom": "16px"
            }),
            html.H3("Lista de Entrevistas"),
            html.Div(id="tabela-entrevistas", style={"marginBottom": "25px"}),

            html.H3("Auditoria de Áudios"),
            html.Div(id="audios-entrevistas")
        ], id="secao-entrevistas", style={
            "background": "#111827",
            "borderRadius": "14px",
            "border": "1px solid #1f2937",
            "padding": "20px",
            "marginTop": "20px"
        }),

        html.Div([
            html.H2("Relatórios", style={
                "marginTop": "0",
                "marginBottom": "16px"
            }),

            html.Div([
                html.A(
                    "📥 Exportar base da pesquisa em Excel",
                    id="link-exportar-excel",
                    href="#",
                    target="_blank",
                    style={
                        "display": "inline-block",
                        "background": "#2563eb",
                        "color": "white",
                        "padding": "12px 18px",
                        "borderRadius": "10px",
                        "textDecoration": "none",
                        "fontWeight": "bold"
                    }
                ),

            

                html.A(
                    "📄 Gerar Relatório PDF",
                    id="link-gerar-pdf",
                    href="#",
                    target="_blank",
                    style={
                        "display": "inline-block",
                        "background": "#16a34a",
                        "color": "white",
                        "padding": "12px 18px",
                        "borderRadius": "10px",
                        "textDecoration": "none",
                        "fontWeight": "bold",
                        "marginLeft": "10px"
                    }
                )

            ], style={
                "background": "#111827",
                "borderRadius": "14px",
                "border": "1px solid #1f2937",
                "padding": "20px",
                "color": "#cbd5e1"
            })
        ], id="secao-relatorios"),
        html.Div([

            html.H2(
                "Inteligência Eleitoral",
                style={"marginBottom": "20px"}
            ),

            html.Div(
                id="inteligencia-conteudo"
            )

        ],
        id="secao-inteligencia",
        style={
            "display": "none"
        }),
                    

    ], style={
        "marginLeft": "260px",
        "padding": "24px",
        "background": "#0f172a",
        "minHeight": "100vh",
        "color": "#e5e7eb",
        "fontFamily": "Arial, sans-serif"
    })

])

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
            html.Div(f"Cliente: {cliente['nome']}", style={
                "fontWeight": "bold",
                "fontSize": "15px"
            }),
            html.Div("Ipsensus Survey", style={
                "fontSize": "13px",
                "color": "#38bdf8",
                "fontWeight": "bold",
                "marginTop": "2px"
            }),
            html.Div("Dashboard de pesquisas em andamento", style={
                "fontSize": "12px",
                "color": "#94a3b8",
                "marginTop": "2px"
            })
        ])
    ], style={
        "display": "flex",
        "alignItems": "center",
        "gap": "10px"
    })

    return options, valor_inicial, header


# =========================
# CALLBACK DASHBOARD

@app.callback(
    [
        Output("kpis", "children"),
        Output("grafico-sexo", "figure"),
        Output("grafico-idade", "figure"),
        Output("mapa-gps", "figure"),
        Output("tabela-entrevistador", "children"),
        Output("tabela-entrevistas", "children"),
        Output("perguntas-dinamicas", "children"),
        Output("audios-entrevistas", "children"),
        Output("filtro-localidade", "options"),
        Output("filtro-entrevistador", "options"),
        Output("pergunta-mapa", "options"),
        Output("pesquisa-header", "children"),
    ],
    [
        Input("pesquisa", "value"),
        Input("filtro-localidade", "value"),
        Input("filtro-entrevistador", "value"),
        Input("pergunta-mapa", "value"),
        Input("tipo-mapa", "value"),
    ]
)
def atualizar_dashboard(pesquisa_id, filtro_localidade, filtro_entrevistador, pergunta_mapa, tipo_mapa):
    
    if not pesquisa_id:
        fig_vazio = tema_fig(px.bar(title="Sem pesquisa selecionada"))
        return [], fig_vazio, fig_vazio, fig_vazio, "", "", "", "", [], [], [], ""

    df = carregar_dados(pesquisa_id)

    if df.empty:
        fig_vazio = tema_fig(px.bar(title="Sem dados"))
        return [
            card("Total", "0", "Sem entrevistas")
        ], fig_vazio, fig_vazio, fig_vazio, "Sem dados", "", "", "", [], [], [], ""

    opcoes_localidade = [
        {"label": x, "value": x}
        for x in sorted(df["localidade"].dropna().unique())
    ]

    opcoes_entrevistador = [
        {"label": x, "value": x}
        for x in sorted(df["entrevistador"].dropna().unique())
    ]

    if filtro_localidade:
        df = df[df["localidade"] == filtro_localidade]

    if filtro_entrevistador:
        df = df[df["entrevistador"] == filtro_entrevistador]

    if df.empty:
        fig_vazio = tema_fig(px.bar(title="Sem dados para o filtro selecionado"))
        return [
            card("Total", "0", "Filtro sem entrevistas")
        ], fig_vazio, fig_vazio, fig_vazio, "Sem dados", "", "", "", opcoes_localidade, opcoes_entrevistador, [], ""

    total = len(df)
    entrevistadores = df["entrevistador"].nunique()

    masc = int((df["sexo"] == "Masculino").sum())
    fem = int((df["sexo"] == "Feminino").sum())

    masc_pct = round((masc / total) * 100, 1) if total else 0
    fem_pct = round((fem / total) * 100, 1) if total else 0

    kpis = [
        card("Entrevistas realizadas", f"{total:,}".replace(",", "."), "Amostra filtrada", "#1d4ed8"),
        card("Masculino", f"{masc_pct}%", f"{masc} entrevistas", "#0f766e"),
        card("Feminino", f"{fem_pct}%", f"{fem} entrevistas", "#be185d"),
        card("Entrevistadores", entrevistadores, "Equipe em campo", "#7e22ce"),
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

    tabela_entrevistas = dash_table.DataTable(
        data=df[[
            "id",
            "submission_id",
            "entrevistador",
            "localidade",
            "sexo",
            "idade"
        ]].head(300).to_dict("records"),
        columns=[
            {"name": "ID", "id": "id"},
            {"name": "Submission", "id": "submission_id"},
            {"name": "Entrevistador", "id": "entrevistador"},
            {"name": "Localidade", "id": "localidade"},
            {"name": "Sexo", "id": "sexo"},
            {"name": "Idade", "id": "idade"},
        ],
        page_size=15,
        filter_action="native",
        sort_action="native",
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
            "padding": "8px",
            "fontSize": "12px",
            "textAlign": "left",
            "maxWidth": "220px",
            "overflow": "hidden",
            "textOverflow": "ellipsis"
        },
    )    

    gps_df = extrair_gps(df)

    if not gps_df.empty and pergunta_mapa:
        mapa_respostas = {}

        for _, row in df.iterrows():
            dados = normalizar_json(row.get("dados"))
            submission = row.get("submission_id")
            mapa_respostas[submission] = dados.get(pergunta_mapa)

        gps_df["resposta_mapa"] = gps_df["submission_id"].map(mapa_respostas)

    if gps_df.empty:

        fig_mapa = tema_fig(
            px.scatter(title="Sem GPS disponível nesta pesquisa")
        )

    else:

        if tipo_mapa == "calor":

            fig_mapa = px.density_mapbox(
                gps_df,
                lat="lat",
                lon="lon",
                radius=35,
                zoom=12,
                height=650,
                title="Mapa de Calor das Entrevistas"
            )

        elif pergunta_mapa and "resposta_mapa" in gps_df.columns:

            gps_df["resposta_mapa"] = gps_df["resposta_mapa"].fillna("Não informado")

            fig_mapa = px.scatter_mapbox(
                gps_df,
                lat="lat",
                lon="lon",
                color="resposta_mapa",

                color_discrete_map={
                    resposta: cor_resposta_mapa(resposta)
                    for resposta in gps_df["resposta_mapa"].unique()
                },

                hover_name="localidade",
                hover_data=[
                    "entrevistador",
                    "accuracy",
                    "resposta_mapa"
                ],
                zoom=12,
                height=650,
                title="Mapa por Resposta da Pergunta"
            )
        else:

            fig_mapa = px.scatter_mapbox(
                gps_df,
                lat="lat",
                lon="lon",
                hover_name="localidade",
                hover_data=[
                    "entrevistador",
                    "accuracy"
                ],
                zoom=12,
                height=650,
                size=[14] * len(gps_df),
                title="Mapa de Pontos das Entrevistas"
            )

        fig_mapa.update_layout(
            mapbox_style="open-street-map",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            font_color="#e5e7eb",
            margin=dict(l=0, r=0, t=50, b=0)
        )

    perguntas = gerar_graficos_perguntas(df, pesquisa_id, pergunta_mapa)
    audios = carregar_audios(pesquisa_id)

    if not perguntas:
        perguntas = [
            html.Div("Nenhuma pergunta encontrada no campo dados JSONB.", style={
                "background": "#111827",
                "padding": "20px",
                "borderRadius": "18px"
            })
        ]
    perguntas_mapa_df = pd.read_sql(
        text("""
            SELECT UPPER(name) AS name, label
            FROM perguntas_pesquisa
            WHERE pesquisa_id = :pesquisa_id
            AND exibir_dashboard = true
            ORDER BY id
        """),
        engine,
        params={"pesquisa_id": pesquisa_id}
    )

    opcoes_pergunta_mapa = [
        {"label": row["label"], "value": row["name"]}
        for _, row in perguntas_mapa_df.iterrows()
    ]
    
    pesquisa_nome = ""

    try:
        pesquisa_nome = [
            opt["label"]
            for opt in lista_pesquisas(session.get("cliente_id"))
            if opt["value"] == pesquisa_id
        ][0]
    except:
        pesquisa_nome = f"Pesquisa ID {pesquisa_id}"

    pesquisa_header = html.Div([
        html.Div(f"Pesquisa: {pesquisa_nome}"),
        html.Div(f"Entrevistas filtradas: {total}")
    ])
    return (
        kpis,
        fig_sexo,
        fig_idade,
        fig_mapa,
        tabela_ent,
        tabela_entrevistas,
        perguntas,
        audios,
        opcoes_localidade,
        opcoes_entrevistador,
        opcoes_pergunta_mapa,
        pesquisa_header
    )

# =========================
# CALLBACK INTELIGÊNCIA
# =========================
@app.callback(
    Output("inteligencia-conteudo", "children"),
    Input("pesquisa", "value")
)
def gerar_inteligencia(pesquisa_id):

    if not pesquisa_id:
        return html.Div("Selecione uma pesquisa para gerar a inteligência.", style={"color": "#cbd5e1"})

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return html.Div("Sem dados para gerar inteligência.", style={"color": "#cbd5e1"})

    total = len(df)

    sexo_top = df["sexo"].value_counts().idxmax() if "sexo" in df.columns and not df["sexo"].empty else "Não informado"
    idade_top = df["idade"].value_counts().idxmax() if "idade" in df.columns and not df["idade"].empty else "Não informado"
    loc_top = df["localidade"].value_counts().idxmax() if "localidade" in df.columns and not df["localidade"].empty else "Não informado"
    entrevistador_top = df["entrevistador"].value_counts().idxmax() if "entrevistador" in df.columns and not df["entrevistador"].empty else "Não informado"

    pct_fem = round((df["sexo"].eq("Feminino").sum() / total) * 100, 1) if total else 0
    pct_masc = round((df["sexo"].eq("Masculino").sum() / total) * 100, 1) if total else 0

    localidades_top = df["localidade"].value_counts().head(5).reset_index()
    localidades_top.columns = ["Localidade", "Entrevistas"]
    localidades_top["%"] = (localidades_top["Entrevistas"] / total * 100).round(1)

    tabela_localidades = dash_table.DataTable(
        data=localidades_top.to_dict("records"),
        columns=[{"name": c, "id": c} for c in localidades_top.columns],
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
            "padding": "9px",
            "textAlign": "left"
        },
        page_size=5
    )

    resumo = (
        f"A pesquisa possui {total} entrevistas válidas. "
        f"O perfil predominante da amostra é {sexo_top}, com maior concentração na faixa etária {idade_top}. "
        f"A localidade com maior volume de entrevistas é {loc_top}. "
        f"A distribuição por sexo apresenta {pct_fem}% de mulheres e {pct_masc}% de homens. "
        f"O entrevistador com maior número de registros é {entrevistador_top}."
    )

    return html.Div([

        html.Div([
            card("Total de entrevistas", f"{total:,}".replace(",", "."), "Base válida"),
            card("Perfil predominante", sexo_top, f"Feminino {pct_fem}% | Masculino {pct_masc}%"),
            card("Faixa etária líder", idade_top, "Maior presença na amostra"),
            card("Localidade líder", loc_top, "Maior concentração territorial"),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(4, 1fr)",
            "gap": "18px",
            "marginBottom": "22px"
        }),

        html.Div([
            html.H3("Resumo Executivo Automático", style={"marginTop": "0"}),
            html.P(resumo, style={
                "fontSize": "16px",
                "lineHeight": "1.6",
                "color": "#e5e7eb"
            })
        ], style={
            "background": "#111827",
            "borderRadius": "14px",
            "border": "1px solid #1f2937",
            "padding": "20px",
            "marginBottom": "22px"
        }),

        html.Div([
            html.H3("Top 5 Localidades", style={"marginTop": "0"}),
            tabela_localidades
        ], style={
            "background": "#111827",
            "borderRadius": "14px",
            "border": "1px solid #1f2937",
            "padding": "20px"
        })

    ])

ODK_URL = "https://app.ar7pesquisas.com.br"
ODK_USER = "augusto.estatistico@gmail.com"
ODK_PASS = "@Mat050dois"

@app.callback(
    Output("link-exportar-excel", "href"),
    Input("pesquisa", "value")
)
def atualizar_link_excel(pesquisa_id):

    if not pesquisa_id:
        return "#"

    return f"/exportar_excel/{pesquisa_id}"

@app.callback(
    Output("link-gerar-pdf", "href"),
    Input("pesquisa", "value")
)
def atualizar_link_pdf(pesquisa_id):

    if not pesquisa_id:
        return "#"

    return f"/gerar_pdf/{pesquisa_id}"


# =========================
# CALLBACK MENU POR SEÇÃO
# =========================
@app.callback(
    Output("secao-ativa", "data"),
    [
        Input("btn-visao-geral", "n_clicks"),
        Input("btn-entrevistas", "n_clicks"),
        Input("btn-mapas", "n_clicks"),
        Input("btn-perguntas", "n_clicks"),
        Input("btn-entrevistadores", "n_clicks"),
        Input("btn-relatorios", "n_clicks"),
        Input("btn-inteligencia", "n_clicks"),
        
    ]
)
def mudar_secao(n1, n2, n3, n4, n5, n6, n7):
    ctx = dash.callback_context

    if not ctx.triggered:
        return "visao-geral"

    botao = ctx.triggered[0]["prop_id"].split(".")[0]

    mapa = {
        "btn-visao-geral": "visao-geral",
        "btn-entrevistas": "entrevistas",
        "btn-mapas": "mapas",
        "btn-perguntas": "perguntas",
        "btn-entrevistadores": "entrevistadores",
        "btn-relatorios": "relatorios",
        "btn-inteligencia": "inteligencia",
    }

    return mapa.get(botao, "visao-geral")


@app.callback(
    [
        Output("secao-visao-geral", "style"),
        Output("secao-entrevistas", "style"),
        Output("secao-mapas", "style"),
        Output("secao-perguntas", "style"),
        Output("secao-entrevistadores", "style"),
        Output("secao-relatorios", "style"),
        Output("secao-inteligencia", "style"),
    ],
    Input("secao-ativa", "data")
)
def exibir_secao(secao):
    base = {"display": "block", "marginBottom": "20px"}
    oculto = {"display": "none"}

    style_entrevistas = {
        "display": "block",
        "background": "#111827",
        "borderRadius": "14px",
        "border": "1px solid #1f2937",
        "padding": "20px",
        "marginTop": "20px"
    }

    style_entrevistadores = {
        "display": "block",
        "background": "#111827",
        "borderRadius": "14px",
        "border": "1px solid #1f2937",
        "padding": "18px"
    }

    return (
        base if secao == "visao-geral" else oculto,
        style_entrevistas if secao == "entrevistas" else oculto,
        base if secao == "mapas" else oculto,
        base if secao == "perguntas" else oculto,
        style_entrevistadores if secao == "entrevistadores" else oculto,
        base if secao == "relatorios" else oculto,
        base if secao == "inteligencia" else oculto,
    )

# =========================
# AUDIO ENDPOINT
# =========================
@server.route("/audio/<int:pesquisa_id>/<path:submission_id>/<path:nome_arquivo>")
def ouvir_audio(pesquisa_id, submission_id, nome_arquivo):

    if "cliente_id" not in session:
        return "Não autorizado", 403

    df = pd.read_sql(
        text("""
            SELECT projeto_odk, form_id
            FROM pesquisas
            WHERE id = :pesquisa_id
        """),
        engine,
        params={"pesquisa_id": pesquisa_id}
    )

    if df.empty:
        return "Pesquisa não encontrada", 404

    projeto_odk = df.iloc[0]["projeto_odk"]
    form_id = df.iloc[0]["form_id"]

    import urllib.parse
    import tempfile
    import subprocess
    import requests
    from requests.auth import HTTPBasicAuth

    submission_encoded = urllib.parse.quote(submission_id, safe="")
    arquivo_encoded = urllib.parse.quote(nome_arquivo, safe="")

    url = (
        f"https://app.ar7pesquisas.com.br/v1/projects/{projeto_odk}"
        f"/forms/{form_id}"
        f"/submissions/{submission_encoded}"
        f"/attachments/{arquivo_encoded}"
    )

    r = requests.get(
        url,
        auth=HTTPBasicAuth(
            "augusto.estatistico@gmail.com",
            "@Mat050dois"
        )
    )

    if r.status_code != 200:
        return f"Erro ao buscar áudio: {r.status_code}", 500

    with tempfile.NamedTemporaryFile(suffix=".amr", delete=False) as entrada:
        entrada.write(r.content)
        entrada_path = entrada.name

    saida_path = entrada_path.replace(".amr", ".mp3")

    processo = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", entrada_path,
            "-acodec", "libmp3lame",
            "-ab", "64k",
            saida_path
        ],
        capture_output=True,
        text=True
    )

    if processo.returncode != 0:
        return f"Erro ao converter áudio: {processo.stderr}", 500

    with open(saida_path, "rb") as f:
        audio_mp3 = f.read()

    return Response(
        audio_mp3,
        mimetype="audio/mpeg"
    )
# =========================
# EXPORTAR EXCEL
# =========================
@server.route("/exportar_excel/<int:pesquisa_id>")
def exportar_excel(pesquisa_id):

    if "cliente_id" not in session:
        return "Não autorizado", 403

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return "Sem dados", 404

    dados_json = df["dados"].apply(normalizar_json)
    json_df = pd.json_normalize(dados_json)

    df_export = pd.concat(
        [df.drop(columns=["dados"]), json_df],
        axis=1
    )

    import io

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="base")

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=pesquisa_{pesquisa_id}.xlsx"
        }
    )
# =========================
# GERAR PDF
# =========================
@server.route("/gerar_pdf/<int:pesquisa_id>")
def gerar_pdf(pesquisa_id):

    if "cliente_id" not in session:
        return "Não autorizado", 403

    df = carregar_dados(pesquisa_id)

    if df.empty:
        return "Sem dados", 404

    cliente = get_cliente(session.get("cliente_id"))

    try:
        pesquisa_nome = [
            opt["label"]
            for opt in lista_pesquisas(session.get("cliente_id"))
            if opt["value"] == pesquisa_id
        ][0]
    except:
        pesquisa_nome = f"Pesquisa ID {pesquisa_id}"

    dados_json = df["dados"].apply(normalizar_json)
    json_df = pd.json_normalize(dados_json)

    perguntas_df = pd.read_sql(
        text("""
            SELECT UPPER(name) AS name, label
            FROM perguntas_pesquisa
            WHERE pesquisa_id = :pesquisa_id
            AND exibir_dashboard = true
            ORDER BY id
        """),
        engine,
        params={"pesquisa_id": pesquisa_id}
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elementos = []
    elementos.append(Paragraph("<b>RELATÓRIO DE PESQUISA</b>", styles["Title"]))
    elementos.append(Spacer(1, 18))
    elementos.append(Paragraph(f"<b>Cliente:</b> {cliente['nome']}", styles["Normal"]))
    elementos.append(Paragraph(f"<b>Pesquisa:</b> {pesquisa_nome}", styles["Normal"]))
    elementos.append(Paragraph(f"<b>Total de entrevistas:</b> {len(df)}", styles["Normal"]))
    elementos.append(Spacer(1, 24))

    elementos.append(Paragraph("<b>1. Resumo Executivo</b>", styles["Heading1"]))

    total = len(df)
    masc = int((df["sexo"] == "Masculino").sum())
    fem = int((df["sexo"] == "Feminino").sum())
    entrevistadores = df["entrevistador"].nunique()

    masc_pct = round(masc / total * 100, 1) if total else 0
    fem_pct = round(fem / total * 100, 1) if total else 0

    elementos.append(Paragraph(f"Entrevistas realizadas: <b>{total}</b>", styles["Normal"]))
    elementos.append(Paragraph(f"Masculino: <b>{masc}</b> entrevistas ({masc_pct}%)", styles["Normal"]))
    elementos.append(Paragraph(f"Feminino: <b>{fem}</b> entrevistas ({fem_pct}%)", styles["Normal"]))
    elementos.append(Paragraph(f"Entrevistadores em campo: <b>{entrevistadores}</b>", styles["Normal"]))
    elementos.append(Spacer(1, 18))

    elementos.append(Paragraph("<b>2. Perfil da Amostra</b>", styles["Heading1"]))

    for coluna, titulo in [
        ("sexo", "Sexo"),
        ("idade", "Faixa Etária"),
        ("localidade", "Localidade"),
        ("entrevistador", "Entrevistador")
    ]:
        elementos.append(Paragraph(f"<b>{titulo}</b>", styles["Heading2"]))

        resumo = df[coluna].value_counts().reset_index()
        resumo.columns = ["Categoria", "Quantidade"]

        for _, row in resumo.iterrows():
            pct = round(row["Quantidade"] / total * 100, 1)
            elementos.append(
                Paragraph(
                    f"{row['Categoria']}: {row['Quantidade']} ({pct}%)",
                    styles["Normal"]
                )
            )

        elementos.append(Spacer(1, 10))

    elementos.append(PageBreak())

    elementos.append(Paragraph("<b>3. Resultados das Perguntas</b>", styles["Heading1"]))

    for _, pergunta in perguntas_df.iterrows():

        nome_coluna = pergunta["name"]
        label = pergunta["label"]

        coluna_real = None

        for c in json_df.columns:
            if c.upper() == nome_coluna:
                coluna_real = c
                break

        if coluna_real is None:
            continue

        serie = json_df[coluna_real].dropna().astype(str).str.strip()
        serie = serie[serie != ""]

        if serie.empty:
            continue

        elementos.append(Paragraph(f"<b>{label}</b>", styles["Heading2"]))

        contagem = serie.value_counts().reset_index()
        contagem.columns = ["Resposta", "Quantidade"]

        base = contagem["Quantidade"].sum()

        for _, row in contagem.iterrows():
            pct = round(row["Quantidade"] / base * 100, 1)
            elementos.append(
                Paragraph(
                    f"{row['Resposta']}: {row['Quantidade']} ({pct}%)",
                    styles["Normal"]
                )
            )

        elementos.append(Spacer(1, 14))

    elementos.append(PageBreak())

    elementos.append(Paragraph("<b>4. Observação Técnica</b>", styles["Heading1"]))
    elementos.append(Paragraph(
        "Relatório gerado automaticamente pela plataforma Ipsensus Survey, "
        "com base nos dados coletados via ODK, processados no banco Supabase "
        "e visualizados no dashboard operacional.",
        styles["Normal"]
    ))

    doc.build(elementos)

    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=relatorio_{pesquisa_id}.pdf"
        }
    )


# =========================
# ETL ENDPOINT
# =========================
@server.route("/etl")
def rodar_etl():
    token = request.args.get("token")

    if token != "123456":
        return "Acesso negado", 403

    resultado = subprocess.run(
        [sys.executable, "etl.py"],
        capture_output=True,
        text=True,
        timeout=600
    )

    return f"""
    <h2>ETL executado</h2>
    <h3>Saída</h3>
    <pre>{resultado.stdout}</pre>
    <h3>Erros</h3>
    <pre>{resultado.stderr}</pre>
    <h3>Código retorno</h3>
    <pre>{resultado.returncode}</pre>
    """

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port)
