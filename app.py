import pandas as pd
import psycopg2
from flask import Flask, request, session, redirect
import dash
from dash import dcc, html, Input, Output
import plotly.express as px

# =========================
# CONFIG
# =========================
DB_URL = "SUA_URL_POSTGRES_AQUI"

server = Flask(__name__)
server.secret_key = "123"

# =========================
# FUNÇÃO DE CONEXÃO
# =========================
def get_data():
    conn = psycopg2.connect(DB_URL)
    df = pd.read_sql("SELECT * FROM dados_pesquisa", conn)
    conn.close()

    # 🔥 NORMALIZA COLUNAS (resolve 90% dos erros)
    df.columns = [c.lower() for c in df.columns]

    return df

# =========================
# LOGIN SIMPLES
# =========================
@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        senha = request.form.get("senha")

        # 🔥 VALIDAÇÃO SIMPLES
        if senha == "123":  
            session["logado"] = True

            # 🔥 evita erro de pesquisa_id inexistente
            session["pesquisa_id"] = 1

            return redirect("/")
        else:
            return "Senha incorreta"

    return '''
        <form method="post">
            <input type="password" name="senha" placeholder="Senha"/>
            <input type="submit"/>
        </form>
    '''

@server.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# DASH APP
# =========================
app = dash.Dash(__name__, server=server, url_base_pathname="/")

app.layout = html.Div([
    html.H2("DASHBOARD DE PESQUISA"),

    html.Div(id="kpis"),

    dcc.Dropdown(id="pergunta"),

    dcc.Graph(id="grafico")
])

# =========================
# CALLBACK
# =========================
@app.callback(
    Output("kpis", "children"),
    Output("grafico", "figure"),
    Output("pergunta", "options"),
    Input("pergunta", "value")
)
def atualizar(pergunta):

    # 🔐 PROTEÇÃO LOGIN
    if not session.get("logado"):
        return "Faça login", {}, []

    df = get_data()

    # =========================
    # GARANTE COLUNAS
    # =========================
    if "sexo" not in df.columns:
        df["sexo"] = "Não informado"

    if "idade" not in df.columns:
        df["idade"] = "Não informado"

    # =========================
    # KPI TOTAL
    # =========================
    total = len(df)

    sexo = df["sexo"].value_counts(normalize=True).reset_index()
    sexo.columns = ["sexo", "perc"]

    tabela_sexo = html.Table([
        html.Tr([html.Th("Sexo"), html.Th("%")])] +
        [html.Tr([html.Td(row["sexo"]), html.Td(f"{row['perc']*100:.1f}%")])
         for _, row in sexo.iterrows()]
    )

    kpis = html.Div([
        html.H4(f"Total da Amostra: {total}"),
        tabela_sexo
    ])

    # =========================
    # PERGUNTAS DINÂMICAS
    # =========================
    perguntas = [c for c in df.columns if c not in ["sexo", "idade", "id"]]

    opcoes = [{"label": p, "value": p} for p in perguntas]

    if not pergunta and perguntas:
        pergunta = perguntas[0]

    # =========================
    # GRÁFICO
    # =========================
    if pergunta in df.columns:
        graf = df[pergunta].value_counts(normalize=True).reset_index()
        graf.columns = ["resposta", "perc"]

        fig = px.bar(
            graf,
            x="resposta",
            y="perc",
            text=graf["perc"].apply(lambda x: f"{x*100:.1f}%")
        )

        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis_tickformat=".0%")

    else:
        fig = {}

    return kpis, fig, opcoes


# =========================
# RUN
# =========================
if __name__ == "__main__":
    server.run(debug=True)