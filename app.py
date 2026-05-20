import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
import json
import os
from sqlalchemy import create_engine





DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

app = dash.Dash(__name__)
server = app.server

def tratar_json(x):
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    return json.loads(x)

app.layout = html.Div([

    html.H1("📊 DASHBOARD ONLINE"),

    dcc.Dropdown(id='pesquisa'),

    dcc.Graph(id='grafico'),

    dcc.Interval(id='update', interval=5000)

])

@app.callback(
    Output('grafico', 'figure'),
    Output('pesquisa', 'options'),
    Input('update', 'n_intervals'),
    Input('pesquisa', 'value')
)
def atualizar(n, pesquisa):

    df = pd.read_sql("SELECT * FROM entrevistas", engine)

    if pesquisa:
        df = df[df['pesquisa_id'] == pesquisa]

    df['dados'] = df['dados'].apply(tratar_json)

    df['pres'] = df['dados'].apply(lambda x: x.get('PRES'))

    voto = df['pres'].value_counts().reset_index()

    voto.columns = ['Candidato', 'Votos']

    fig = px.bar(voto, x='Candidato', y='Votos')

    pesquisas = pd.read_sql("SELECT * FROM pesquisas", engine)

    opts = [
        {
            'label': p['nome'],
            'value': p['id']
        }
        for _, p in pesquisas.iterrows()
    ]

    return fig, opts



if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 8050)),
        debug=False
    )