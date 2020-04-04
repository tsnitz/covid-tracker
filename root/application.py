import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests

from dash.dependencies import Input, Output
from plotly.subplots import make_subplots
from urllib.request import HTTPError

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

application = flask.Flask(__name__)
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, server=application)

app.layout = html.Div([
    dcc.Graph(id='indicator-graphic-us'),
    html.Label("y-axis scale"),
    dcc.RadioItems(
        id='yaxis-type-us',
        options=[{'label': i, 'value': i} for i in ['linear', 'log']],
        value='linear',
        labelStyle={'display': 'inline-block'}
    ),
    dcc.Dropdown(id='state-selector',
        # options=[{"label": state, "value": state} for state in all_states],
         # TODO: Pass in all state values here
        options=[{"label": state, "value": state} for state in ["Florida", "Georgia", "Alabama"]],
        value='Georgia'
    ),
    dcc.Graph(id='indicator-graphic-state'),
    html.Label("y-axis scale"),
    dcc.RadioItems(
        id='yaxis-type-state',
        options=[{'label': i, 'value': i} for i in ['linear', 'log']],
        value='linear',
        labelStyle={'display': 'inline-block'}
    ),
    dcc.Markdown("""
    This is intended to supplement the excellent [dashboard](https://coronavirus.jhu.edu/map.html) maintained by The Center for Systems Science and Engineering (CSSE) at Johns Hopkins. Confirmed cases and deaths data come from this dashboard and can be found in their [Git repo](https://github.com/CSSEGISandData/COVID-19).
    Daily testing data can be found [here](https://covidtracking.com/api/us/daily) and is maintained by the [COVID Tracking Project](https://covidtracking.com/)
    """),
    dcc.Dropdown(id='dropdown'),
    # Hidden div inside the app that stores the intermediate value
    html.Div(id='intermediate-value', style={'display': 'none'})
])



@app.callback(Output('intermediate-value', 'children'), [Input('dropdown', 'value')])
def load_data(dummy_var):
    confirmed = pd.read_csv("https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv")
    deaths = pd.read_csv("https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv")

    try:
        r = requests.get(url = "https://covidtracking.com/api/us/daily")
        data = r.json()
        testing_us = pd.DataFrame(data)
        testing_us.to_csv("testing_us.csv", index=False)
    except HTTPError: #This will happen if I spam the server and get temp blocked
        print("Request blocked")

    try:
        testing_us = pd.read_csv("testing_us.csv")
        testing_us["date"] = pd.to_datetime(testing_us["date"], format="%Y%m%d")
        testing_us = testing_us[["date", "total"]].set_index("date").rename(columns={"total": "tested"})
    except HTTPError: #This will happen if I spam the server and get temp blocked
        print("File not found")

    confirmed_us = confirmed[confirmed["Country/Region"] == "US"]
    deaths_us = deaths[deaths["Country/Region"] == "US"]

    drop_columns = ["Province/State", "Country/Region", "Lat", "Long"]
    confirmed_us = confirmed_us.drop(columns=drop_columns).sum()
    confirmed_us.index = pd.to_datetime(confirmed_us.index)
    deaths_us = deaths_us.drop(columns=drop_columns).sum()
    deaths_us.index = pd.to_datetime(deaths_us.index)

    stats_us = pd.concat([testing_us, confirmed_us, deaths_us], axis=1).rename(columns={0: "confirmed", 1: "deaths"})
    stats_us = stats_us.rename_axis("date")
    stats_us["mortality_rate"] = stats_us["deaths"]/stats_us["confirmed"]
    stats_us.index = pd.to_datetime(stats_us.index)
    stats_us = stats_us.sort_index()

    r = requests.get(url = "https://api.github.com/repos/CSSEGISandData/COVID-19/contents/csse_covid_19_data/csse_covid_19_daily_reports")
    data = r.json()

    def return_url_from_file(item):
        if ".csv" in item["path"]:
            return item["download_url"]

    download_urls = [return_url_from_file(item) for item in data]
    download_urls = [item for item in download_urls if item != None]

    reports = []
    country_col = "country"
    state_col = "state"
    for download_url in download_urls:
        df = pd.read_csv(download_url)
        df.columns = [item.lower() for item in df.columns]
        df = df.rename(columns={"province/state": state_col, "province_state": state_col, "country/region": country_col, "country_region": country_col, "last update": "last_update"})
        df = df[["last_update", country_col, state_col, "confirmed", "deaths"]]
        reports.append(df)
    report = pd.concat(reports, axis=0)
    report = report.groupby(["last_update", "country", "state"]).sum().reset_index()

    report_us = report[report["country"] == "US"]
    report_us = report_us[~(report_us["state"].str.contains(",") | report_us["state"].str.contains("Diamond") | report_us["state"].str.contains("Wuhan") | report_us["state"].str.contains("Recovered") | report_us["state"].str.contains("US") | report_us["state"].str.contains("Grand"))]
    report_us["last_update"] = pd.to_datetime(report_us["last_update"])
    report_us = report_us.set_index("last_update").sort_index()

    all_states = report_us["state"].unique()
    all_states.sort()

    outputs = {
        'stats_us': stats_us.to_json(orient='split', date_format='iso'),
        'report_us': report_us.to_json(orient='split', date_format='iso'),
        'all_states': list(all_states)
    }

    return json.dumps(outputs)

@app.callback(
    Output('indicator-graphic-us', 'figure'),
    [Input('yaxis-type-us', 'value'), Input('intermediate-value', 'children')])
def update_indicator_graphic_us(yaxis_type_us, data):
    datasets = json.loads(data)
    stats_us = pd.read_json(datasets['stats_us'], orient='split')

    start_date = pd.Timestamp("2020-03-01").tz_localize('US/Eastern')
    df = stats_us[stats_us.index >= start_date]

    fig = make_subplots(rows=2, cols=1, specs=[[{}], [{"secondary_y": True}]])

    # Add traces
    fig.add_trace(
        go.Scatter(x=df.index, y=df["tested"], name="tested"), row=1, col=1
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["confirmed"], name="confirmed"), row=1, col=1
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["deaths"], name="deaths"), row=2, col=1
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["mortality_rate"] * 100.0, name="mortality rate [%]"), row=2, col=1,
        secondary_y=True,
    )

    # Add figure title
    fig.update_layout(
        title_text="COVID-19 Cases and Mortality Rate (Deaths/Confirmed) for United States",
        legend={"title": "<i>click legend items to add/remove traces</i>"}
    )

    # Set y-axes titles
    fig.update_yaxes(title_text="<b>#<br>people</b> ", secondary_y=False, type=yaxis_type_us)
    fig.update_yaxes(title_text="<b>%</b><br>", secondary_y=True)

    return fig

@app.callback(
    Output('indicator-graphic-state', 'figure'),
    [Input('yaxis-type-state', 'value'), Input('state-selector', 'value'), Input('intermediate-value', 'children')])
def update_indicator_graphic_state(yaxis_type_us, state, data):
    datasets = json.loads(data)
    report_us = pd.read_json(datasets['report_us'], orient='split')
    all_states = list(datasets["all_states"])

    start_date = pd.Timestamp("2020-03-01").tz_localize('US/Eastern')

    stats_state = report_us[report_us["state"] == state]
    stats_state = stats_state.drop(columns=["country", "state"])
    stats_state = stats_state[~stats_state.index.duplicated(keep='last')]
    stats_state["mortality_rate"] = stats_state["deaths"] / stats_state["confirmed"]

    df = stats_state[stats_state.index >= start_date]

    fig = make_subplots(rows=2, cols=1, specs=[[{}], [{"secondary_y": True}]])

    color_sequence = px.colors.qualitative.Plotly

    # Add traces
    fig.add_trace(
        go.Scatter(x=df.index, y=df["confirmed"], name="confirmed", line=dict(color=color_sequence[1])), row=1, col=1
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["deaths"], name="deaths", line=dict(color=color_sequence[2])), row=2, col=1
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["mortality_rate"] * 100.0, name="mortality rate [%]", line=dict(color=color_sequence[3])), row=2, col=1,
        secondary_y=True,
    )

    # Add figure title
    fig.update_layout(
        title_text="COVID-19 Cases and Mortality Rate (Deaths/Confirmed) for {}".format(state),
        legend={"title": "<i>click legend items to add/remove traces</i>"}
    )

    fig.update_xaxes(range=[start_date, pd.Timestamp("today").date()])

    # Set y-axes titles
    fig.update_yaxes(title_text="<b>#<br>people</b> ", secondary_y=False, type=yaxis_type_us)
    fig.update_yaxes(title_text="<b>%</b><br>", secondary_y=True)

    return fig

if __name__ == '__main__':
    app.run_server(debug=True)