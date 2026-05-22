import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import os

# ===== BANCO =====
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL não definida")

engine = create_engine(DATABASE_URL)

# ===== APP =====
app = dash.Dash(__name__)
server = app.server

# ===== LAYOUT =====
app.layout = html.Div([

    html.H1("📊 Dashboard Pesquisa", style={'textAlign': 'center'}),

    dcc.Dropdown(
        id='pesquisa',
        placeholder="Selecione a pesquisa"
    ),

    dcc.Dropdown(
        id='localidade',
        placeholder="Filtrar por localidade"
    ),

    dcc.Graph(id='grafico_sexo'),
    dcc.Graph(id='grafico_idade'),

    dcc.Interval(id='update', interval=5000)

])

# ===== CARREGAR PESQUISAS =====
@app.callback(
    Output('pesquisa', 'options'),
    Input('update', 'n_intervals')
)
def carregar_pesquisas(n):

    df = pd.read_sql("SELECT * FROM pesquisas", engine)

    if df.empty:
        return []

    return [
        {'label': i['nome'], 'value': i['id']}
        for _, i in df.iterrows()
    ]

# ===== CARREGAR LOCALIDADE =====
@app.callback(
    Output('localidade', 'options'),
    Input('pesquisa', 'value')
)
def carregar_localidade(p):

    if not p:
        return []

    df = pd.read_sql(f"""
        SELECT DISTINCT localidade
        FROM entrevistas
        WHERE pesquisa_id = {p}
    """, engine)

    return [
        {'label': i['localidade'], 'value': i['localidade']}
        for _, i in df.iterrows()
        if i['localidade']
    ]

# ===== ATUALIZAR GRÁFICOS =====
@app.callback(
    Output('grafico_sexo', 'figure'),
    Output('grafico_idade', 'figure'),
    Input('pesquisa', 'value'),
    Input('localidade', 'value')
)
def atualizar(p, localidade):

    if not p:
        vazio = px.bar(title="Selecione uma pesquisa")
        return vazio, vazio

    df = pd.read_sql(f"""
        SELECT sexo, idade, localidade
        FROM entrevistas
        WHERE pesquisa_id = {p}
    """, engine)

    if localidade:
        df = df[df['localidade'] == localidade]

    if df.empty:
        vazio = px.bar(title="Sem dados")
        return vazio, vazio

    # ===== SEXO (%) =====
    sexo = df['sexo'].value_counts(normalize=True) * 100
    sexo = sexo.reset_index()
    sexo.columns = ['Sexo', 'Percentual']

    fig_sexo = px.bar(
        sexo,
        x='Sexo',
        y='Percentual',
        text='Percentual',
        title="Sexo (%)"
    )

    fig_sexo.update_traces(texttemplate='%{text:.1f}%', textposition='outside')

    # ===== IDADE (%) =====
    idade = df['idade'].value_counts(normalize=True) * 100
    idade = idade.reset_index()
    idade.columns = ['Idade', 'Percentual']

    fig_idade = px.bar(
        idade,
        x='Idade',
        y='Percentual',
        text='Percentual',
        title="Idade (%)"
    )

    fig_idade.update_traces(texttemplate='%{text:.1f}%', textposition='outside')

    return fig_sexo, fig_idade


# ===== RUN =====
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 8050)),
        debug=False
    )