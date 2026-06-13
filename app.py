import random
import math
from datetime import datetime
import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import anthropic

# ─────────────────────────────────────────────
# 1. SYNTHETIC DATA GENERATION
# ─────────────────────────────────────────────

SITES = ["Chennai-N01", "Chennai-N02", "Mumbai-C03", "Delhi-R04", "Bangalore-S05"]
TECHS = ["5G NR", "4G LTE", "3G UMTS"]
HOURS = [f"{str(i).zfill(2)}:00" for i in range(24)]
DAYS  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

TECH_COLORS = {"5G NR": "#1D9E75", "4G LTE": "#378ADD", "3G UMTS": "#D85A30"}

def seeded_random(seed):
    """Simple deterministic random number generator."""
    s = seed
    def rng():
        nonlocal s
        s = (s * 16807) % 2147483647
        return (s - 1) / 2147483646
    return rng

def generate_hourly_kpis(site, tech, day_idx):
    rng   = seeded_random(ord(site[0]) * 31 + ord(tech[0]) * 7 + day_idx * 13)
    base  = 0.97 if tech == "5G NR" else (0.94 if tech == "4G LTE" else 0.89)
    rows  = []
    prev_prb = 0.3
    for i, hour in enumerate(HOURS):
        load   = 0.3 + 0.6 * math.sin((i - 2) * math.pi / 12) + rng() * 0.1
        noise  = rng() * 0.03
        spike  = -0.12 if (i == 13 and site == "Chennai-N01" and day_idx == 2) else 0
        spike2 = -0.15 if (i == 20 and site == "Mumbai-C03"  and day_idx == 4) else 0
        rsrp   = (-78 - rng()*10) if tech=="5G NR" else ((-82-rng()*12) if tech=="4G LTE" else (-88-rng()*15))
        sinr   = (18+rng()*8-load*5) if tech=="5G NR" else ((14+rng()*6-load*4) if tech=="4G LTE" else (10+rng()*5-load*3))
        dl     = (450+rng()*200-load*80) if tech=="5G NR" else ((120+rng()*60-load*25) if tech=="4G LTE" else (8+rng()*4-load*2))
        prb    = min(0.98, 0.2 + load*0.7 + noise)
        csr    = min(1, max(0.7, base - load*0.04 + noise + spike + spike2))
        drop   = max(0, 0.005 + (1-base)*0.05 + load*0.01 - noise - spike - spike2)
        # Trend for prediction
        prev_prb = prb
        rows.append({
            "hour": hour, "hour_idx": i,
            "csr": round(csr * 100, 2),
            "throughput_dl": round(dl, 1),
            "prb": round(prb * 100, 1),
            "rsrp": round(rsrp, 1),
            "sinr": round(sinr, 1),
            "drop_rate": round(drop * 100, 3),
        })
    return pd.DataFrame(rows)

def build_dataset():
    data = {}
    for site in SITES:
        data[site] = {}
        for tech in TECHS:
            data[site][tech] = [generate_hourly_kpis(site, tech, di) for di in range(7)]
    return data

DATASET = build_dataset()

# ─────────────────────────────────────────────
# 2. ANOMALY DETECTION
# ─────────────────────────────────────────────

def detect_anomalies(df):
    anomalies = []
    avg_csr  = df["csr"].mean()
    avg_drop = df["drop_rate"].mean()
    for _, row in df.iterrows():
        if row["csr"] < avg_csr - 6:
            anomalies.append({"Hour": row["hour"], "Type": "Low Call Setup Success",
                               "Value": f"{row['csr']}%", "Severity": "CRITICAL"})
        if row["drop_rate"] > avg_drop * 2.5 and row["drop_rate"] > 2:
            anomalies.append({"Hour": row["hour"], "Type": "High Drop Rate",
                               "Value": f"{row['drop_rate']}%", "Severity": "WARNING"})
        if row["prb"] > 92:
            anomalies.append({"Hour": row["hour"], "Type": "PRB Congestion",
                               "Value": f"{row['prb']}%", "Severity": "WARNING"})
    return anomalies

# ─────────────────────────────────────────────
# 3. PREDICTIVE FAULT DETECTION
# ─────────────────────────────────────────────

def predict_faults(df):
    predictions = []
    window = 4  # look at last 4 hours trend
    for i in range(window, len(df)):
        recent = df.iloc[i-window:i]
        # PRB trending up fast
        prb_trend = recent["prb"].iloc[-1] - recent["prb"].iloc[0]
        if prb_trend > 10 and df.iloc[i]["prb"] > 75:
            hours_to_critical = max(1, int((92 - df.iloc[i]["prb"]) / (prb_trend / window)))
            predictions.append({
                "Hour": df.iloc[i]["hour"],
                "Prediction": f"PRB congestion predicted in ~{hours_to_critical}h",
                "Current Value": f"{df.iloc[i]['prb']}%",
                "Trend": f"+{prb_trend:.1f}% over last {window}h",
                "Risk": "HIGH" if hours_to_critical <= 2 else "MEDIUM"
            })
        # CSR trending down
        csr_trend = recent["csr"].iloc[-1] - recent["csr"].iloc[0]
        if csr_trend < -3 and df.iloc[i]["csr"] < 93:
            predictions.append({
                "Hour": df.iloc[i]["hour"],
                "Prediction": "CSR degradation likely to worsen",
                "Current Value": f"{df.iloc[i]['csr']}%",
                "Trend": f"{csr_trend:.1f}% over last {window}h",
                "Risk": "HIGH" if df.iloc[i]["csr"] < 90 else "MEDIUM"
            })
    return predictions

# ─────────────────────────────────────────────
# 4. ALARM LOG
# ─────────────────────────────────────────────

def build_alarm_log():
    alarms = []
    statuses = ["Open", "Acknowledged", "Resolved"]
    for site in SITES:
        for tech in TECHS:
            for di, day in enumerate(DAYS):
                df = DATASET[site][tech][di]
                for a in detect_anomalies(df):
                    alarms.append({
                        "Site": site, "Technology": tech, "Day": day,
                        "Hour": a["Hour"], "Alarm Type": a["Type"],
                        "Severity": a["Severity"],
                        "Status": random.choice(statuses)
                    })
    return pd.DataFrame(alarms)

ALARM_LOG = build_alarm_log()

# ─────────────────────────────────────────────
# 5. DASH APP LAYOUT
# ─────────────────────────────────────────────

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "RAN KPI Dashboard"

COLORS = {
    "bg": "#0f1117", "card": "#1a1d27", "border": "#2a2d3a",
    "text": "#e8e6e0", "text2": "#a0a09a", "text3": "#6e6e68",
    "green": "#1D9E75", "blue": "#378ADD", "red": "#E24B4A", "orange": "#D85A30", "yellow": "#BA7517"
}

def card(children, style={}):
    base = {"background": COLORS["card"], "borderRadius": "10px",
            "padding": "16px", "border": f"1px solid {COLORS['border']}",
            "marginBottom": "16px"}
    base.update(style)
    return html.Div(children, style=base)

def label(text):
    return html.Div(text, style={"fontSize": "11px", "fontWeight": "500",
                                  "color": COLORS["text2"], "letterSpacing": "0.05em",
                                  "textTransform": "uppercase", "marginBottom": "8px"})

app.layout = html.Div([
    # Header
    html.Div([
        html.Div([
            html.H2("RAN KPI Dashboard", style={"margin": 0, "fontSize": "20px", "fontWeight": "500"}),
            html.Div("Network Design & Optimisation · Predictive AIOps", style={"fontSize": "13px", "color": COLORS["text2"], "marginTop": "4px"})
        ]),
        html.Div([
            dcc.Dropdown(SITES, SITES[0], id="site-dd", clearable=False,
                         style={"width": "160px", "fontSize": "13px"}),
            dcc.Dropdown(TECHS, TECHS[0], id="tech-dd", clearable=False,
                         style={"width": "120px", "fontSize": "13px"}),
            dcc.Dropdown(DAYS, DAYS[0], id="day-dd", clearable=False,
                         style={"width": "100px", "fontSize": "13px"}),
        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap"})
    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start",
              "flexWrap": "wrap", "gap": "12px", "marginBottom": "20px",
              "padding": "16px 20px", "background": COLORS["card"],
              "borderRadius": "10px", "border": f"1px solid {COLORS['border']}"}),

    # KPI Summary Cards
    html.Div(id="kpi-cards", style={"display": "grid",
             "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
             "gap": "12px", "marginBottom": "16px"}),

    # Tabs
    dcc.Tabs(id="tabs", value="overview", children=[
        dcc.Tab(label="Overview",    value="overview",    style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['green']}"}),
        dcc.Tab(label="Trends",      value="trends",      style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['green']}"}),
        dcc.Tab(label="Anomalies",   value="anomalies",   style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['red']}"}),
        dcc.Tab(label="Predictions", value="predictions", style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['yellow']}"}),
        dcc.Tab(label="Alarm Log",   value="alarms",      style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['orange']}"}),
        dcc.Tab(label="Site Compare",value="sites",       style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid {COLORS['blue']}"}),
        dcc.Tab(label="AI Assistant",value="ai",          style={"color": COLORS["text2"]}, selected_style={"color": COLORS["text"], "borderTop": f"2px solid #a855f7"}),
    ], style={"marginBottom": "16px"}),

    html.Div(id="tab-content"),

], style={"background": COLORS["bg"], "minHeight": "100vh", "padding": "20px",
          "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          "color": COLORS["text"]})

# ─────────────────────────────────────────────
# 6. CALLBACKS
# ─────────────────────────────────────────────

def get_df(site, tech, day):
    return DATASET[site][tech][DAYS.index(day)]

@app.callback(Output("kpi-cards", "children"),
              [Input("site-dd","value"), Input("tech-dd","value"), Input("day-dd","value")])
def update_kpi_cards(site, tech, day):
    df = get_df(site, tech, day)
    anomalies = detect_anomalies(df)
    cards_data = [
        ("Avg Call Setup Success", f"{df['csr'].mean():.1f}%",
         COLORS["green"] if df['csr'].mean() >= 95 else COLORS["yellow"] if df['csr'].mean() >= 90 else COLORS["red"],
         "threshold: 95%"),
        ("Avg DL Throughput",
         f"{df['throughput_dl'].mean():.0f} Mbps" if df['throughput_dl'].mean() < 1000 else f"{df['throughput_dl'].mean()/1000:.1f} Gbps",
         COLORS["blue"], f"{'5G target: 400 Mbps' if tech=='5G NR' else '4G target: 100 Mbps' if tech=='4G LTE' else '3G target: 6 Mbps'}"),
        ("Peak PRB Utilization", f"{df['prb'].max():.1f}%",
         COLORS["red"] if df['prb'].max() > 90 else COLORS["yellow"] if df['prb'].max() > 75 else COLORS["green"],
         "congestion > 90%"),
        ("Avg RSRP", f"{df['rsrp'].mean():.1f} dBm",
         COLORS["green"] if df['rsrp'].mean() > -85 else COLORS["yellow"] if df['rsrp'].mean() > -95 else COLORS["red"],
         "good: > -85 dBm"),
        ("Anomalies Detected", str(len(anomalies)),
         COLORS["red"] if len(anomalies) > 3 else COLORS["yellow"] if len(anomalies) > 0 else COLORS["green"],
         f"on {day}"),
    ]
    return [
        html.Div([
            html.Div(c[0], style={"fontSize": "11px", "color": COLORS["text2"], "marginBottom": "6px"}),
            html.Div(c[1], style={"fontSize": "22px", "fontWeight": "500", "color": c[2]}),
            html.Div(c[3], style={"fontSize": "11px", "color": COLORS["text3"], "marginTop": "4px"}),
        ], style={"background": COLORS["card"], "borderRadius": "10px", "padding": "14px",
                  "border": f"1px solid {COLORS['border']}"})
        for c in cards_data
    ]

@app.callback(Output("tab-content", "children"),
              [Input("tabs","value"), Input("site-dd","value"),
               Input("tech-dd","value"), Input("day-dd","value")])
def update_tab(tab, site, tech, day):
    df = get_df(site, tech, day)
    color = TECH_COLORS[tech]

    # ── OVERVIEW ──
    if tab == "overview":
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df["hour"], y=df["csr"], mode="lines",
                                   line=dict(color=color, width=2), name="CSR (%)"))
        fig1.add_hline(y=95, line_dash="dash", line_color=COLORS["yellow"],
                       annotation_text="95% threshold", annotation_position="top right")
        for a in detect_anomalies(df):
            if a["Type"] == "Low Call Setup Success":
                fig1.add_vline(x=a["Hour"], line_color=COLORS["red"], opacity=0.3)
        fig1.update_layout(title="Call Setup Success Rate – 24h", **chart_layout())

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df["hour"], y=df["throughput_dl"], mode="lines",
                                   line=dict(color=COLORS["blue"], width=2), name="DL (Mbps)", yaxis="y1"))
        fig2.add_trace(go.Scatter(x=df["hour"], y=df["prb"], mode="lines",
                                   line=dict(color=COLORS["orange"], width=1.5, dash="dash"),
                                   name="PRB (%)", yaxis="y2"))
        fig2.update_layout(title="DL Throughput & PRB Utilization",
                           yaxis2=dict(title="PRB %", overlaying="y", side="right", color=COLORS["text2"]),
                           **chart_layout())

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=df["hour"], y=df["rsrp"], mode="lines",
                                   line=dict(color=COLORS["green"], width=2), name="RSRP (dBm)"))
        fig3.add_hline(y=-85, line_dash="dash", line_color=COLORS["yellow"],
                       annotation_text="Good threshold (-85 dBm)")
        fig3.update_layout(title="Signal Strength (RSRP)", **chart_layout())

        return html.Div([
            card(dcc.Graph(figure=fig1, config={"displayModeBar": False})),
            card(dcc.Graph(figure=fig2, config={"displayModeBar": False})),
            card(dcc.Graph(figure=fig3, config={"displayModeBar": False})),
        ])

    # ── TRENDS ──
    elif tab == "trends":
        weekly = []
        for di, d in enumerate(DAYS):
            wdf = DATASET[site][tech][di]
            weekly.append({
                "day": d, "csr": round(wdf["csr"].mean(), 2),
                "dl": round(wdf["throughput_dl"].mean(), 1),
                "anomalies": len(detect_anomalies(wdf))
            })
        wdf = pd.DataFrame(weekly)

        fig1 = go.Figure(go.Bar(x=wdf["day"], y=wdf["csr"], marker_color=color,
                                 name="CSR (%)", marker_line_width=0))
        fig1.add_hline(y=95, line_dash="dash", line_color=COLORS["yellow"])
        fig1.update_layout(title="Weekly Average CSR", **chart_layout())

        fig2 = go.Figure(go.Bar(x=wdf["day"], y=wdf["dl"], marker_color=COLORS["blue"],
                                 name="DL (Mbps)", marker_line_width=0))
        fig2.update_layout(title="Weekly Average DL Throughput", **chart_layout())

        fig3 = go.Figure(go.Bar(x=wdf["day"], y=wdf["anomalies"], marker_color=COLORS["red"],
                                 name="Anomalies", marker_line_width=0))
        fig3.update_layout(title="Daily Anomaly Count", **chart_layout())

        return html.Div([
            card(dcc.Graph(figure=fig1, config={"displayModeBar": False})),
            card(dcc.Graph(figure=fig2, config={"displayModeBar": False})),
            card(dcc.Graph(figure=fig3, config={"displayModeBar": False})),
        ])

    # ── ANOMALIES ──
    elif tab == "anomalies":
        anomalies = detect_anomalies(df)
        if not anomalies:
            return card(html.Div("✅ No anomalies detected for this selection.",
                                  style={"textAlign": "center", "color": COLORS["green"], "padding": "30px"}))
        rows = []
        for a in anomalies:
            sev_color = COLORS["red"] if a["Severity"] == "CRITICAL" else COLORS["yellow"]
            rows.append(html.Div([
                html.Div([
                    html.Div(a["Type"], style={"fontWeight": "500", "fontSize": "14px"}),
                    html.Div(f"Hour: {a['Hour']} · {site} · {tech}", style={"fontSize": "12px", "color": COLORS["text2"], "marginTop": "2px"}),
                ]),
                html.Div([
                    html.Div(a["Value"], style={"fontSize": "16px", "fontWeight": "500", "color": sev_color}),
                    html.Span(a["Severity"], style={"fontSize": "11px", "background": sev_color,
                               "color": "#fff", "padding": "2px 8px", "borderRadius": "4px", "marginLeft": "8px"})
                ], style={"display": "flex", "alignItems": "center"})
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                      "background": COLORS["bg"], "borderRadius": "8px", "padding": "12px 16px",
                      "borderLeft": f"3px solid {sev_color}", "marginBottom": "8px"}))

        recs = []
        types = [a["Type"] for a in anomalies]
        if "Low Call Setup Success" in types:
            recs.append("↳ CSR degradation — Check interference on neighboring cells. Consider antenna tilt optimization or load balancing to adjacent sectors.")
        if "PRB Congestion" in types:
            recs.append("↳ PRB congestion — Evaluate carrier aggregation enablement or inter-frequency handover thresholds.")
        if "High Drop Rate" in types:
            recs.append("↳ Elevated drop rate — Verify handover parameters (A3 offset, TTT). Check backhaul link quality and transport alarms.")

        return html.Div([
            card([html.Div(f"Detected {len(anomalies)} anomalies on {day} for {site} · {tech}",
                           style={"fontSize": "13px", "color": COLORS["text2"], "marginBottom": "12px"})] + rows),
            card([
                html.Div("Automated Root Cause Recommendations", style={"fontWeight": "500", "marginBottom": "12px"}),
                *[html.Div(r, style={"fontSize": "13px", "color": COLORS["text2"],
                                      "lineHeight": "1.7", "marginBottom": "8px"}) for r in recs]
            ])
        ])

    # ── PREDICTIONS ──
    elif tab == "predictions":
        preds = predict_faults(df)
        if not preds:
            return card(html.Div("✅ No fault predictions for this selection. Network looks stable.",
                                  style={"textAlign": "center", "color": COLORS["green"], "padding": "30px"}))
        rows = []
        for p in preds:
            risk_color = COLORS["red"] if p["Risk"] == "HIGH" else COLORS["yellow"]
            rows.append(html.Div([
                html.Div([
                    html.Div(p["Prediction"], style={"fontWeight": "500", "fontSize": "14px"}),
                    html.Div(f"At {p['Hour']} · Trend: {p['Trend']}", style={"fontSize": "12px", "color": COLORS["text2"], "marginTop": "2px"}),
                ]),
                html.Div([
                    html.Div(p["Current Value"], style={"fontSize": "15px", "fontWeight": "500", "color": risk_color}),
                    html.Span(p["Risk"] + " RISK", style={"fontSize": "11px", "background": risk_color,
                               "color": "#fff", "padding": "2px 8px", "borderRadius": "4px", "marginLeft": "8px"})
                ], style={"display": "flex", "alignItems": "center"})
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                      "background": COLORS["bg"], "borderRadius": "8px", "padding": "12px 16px",
                      "borderLeft": f"3px solid {risk_color}", "marginBottom": "8px"}))

        # PRB trend chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["hour"], y=df["prb"], mode="lines",
                                  line=dict(color=COLORS["yellow"], width=2), name="PRB (%)"))
        fig.add_hline(y=92, line_dash="dash", line_color=COLORS["red"],
                      annotation_text="Critical threshold (92%)")
        fig.update_layout(title="PRB Utilization Trend (Prediction Reference)", **chart_layout())

        return html.Div([
            card([
                html.Div("⚠️ Predictive Fault Detection", style={"fontWeight": "500", "fontSize": "15px", "marginBottom": "4px"}),
                html.Div("Faults predicted based on KPI trend analysis — before they happen.",
                         style={"fontSize": "12px", "color": COLORS["text2"], "marginBottom": "14px"}),
            ] + rows),
            card(dcc.Graph(figure=fig, config={"displayModeBar": False}))
        ])

    # ── ALARM LOG ──
    elif tab == "alarms":
        filtered = ALARM_LOG[ALARM_LOG["Site"] == site] if site else ALARM_LOG
        sev_counts = filtered["Severity"].value_counts()
        status_counts = filtered["Status"].value_counts()

        fig1 = go.Figure(go.Bar(
            x=sev_counts.index, y=sev_counts.values,
            marker_color=[COLORS["red"] if s == "CRITICAL" else COLORS["yellow"] for s in sev_counts.index]
        ))
        fig1.update_layout(title="Alarms by Severity", **chart_layout())

        fig2 = go.Figure(go.Pie(
            labels=status_counts.index, values=status_counts.values,
            marker_colors=[COLORS["red"], COLORS["yellow"], COLORS["green"]]
        ))
        fig2.update_layout(title="Alarm Status Distribution", **chart_layout())

        return html.Div([
            html.Div([
                card(dcc.Graph(figure=fig1, config={"displayModeBar": False}), style={"flex": 1}),
                card(dcc.Graph(figure=fig2, config={"displayModeBar": False}), style={"flex": 1}),
            ], style={"display": "flex", "gap": "12px"}),
            card(dash_table.DataTable(
                data=filtered.head(50).to_dict("records"),
                columns=[{"name": c, "id": c} for c in filtered.columns],
                style_table={"overflowX": "auto"},
                style_header={"background": COLORS["border"], "color": COLORS["text"],
                               "fontWeight": "500", "fontSize": "12px", "border": "none"},
                style_cell={"background": COLORS["bg"], "color": COLORS["text2"],
                             "fontSize": "12px", "border": f"1px solid {COLORS['border']}", "padding": "8px"},
                style_data_conditional=[
                    {"if": {"filter_query": '{Severity} = "CRITICAL"'}, "color": COLORS["red"]},
                    {"if": {"filter_query": '{Status} = "Open"'}, "fontWeight": "500"},
                ],
                page_size=15,
                sort_action="native",
                filter_action="native",
            ))
        ])

    # ── SITE COMPARE ──
    elif tab == "sites":
        rows = []
        for s in SITES:
            sdf = DATASET[s][tech][DAYS.index(day)]
            rows.append({
                "Site": s, "CSR (%)": round(sdf["csr"].mean(), 2),
                "DL (Mbps)": round(sdf["throughput_dl"].mean(), 1),
                "Peak PRB (%)": round(sdf["prb"].max(), 1),
                "Avg RSRP (dBm)": round(sdf["rsrp"].mean(), 1),
                "Anomalies": len(detect_anomalies(sdf))
            })
        cdf = pd.DataFrame(rows)

        fig1 = go.Figure(go.Bar(y=cdf["Site"], x=cdf["CSR (%)"], orientation="h",
                                 marker_color=TECH_COLORS[tech], marker_line_width=0))
        fig1.add_vline(x=95, line_dash="dash", line_color=COLORS["yellow"])
        fig1.update_layout(title="CSR by Site", **chart_layout())

        fig2 = go.Figure(go.Bar(y=cdf["Site"], x=cdf["DL (Mbps)"], orientation="h",
                                 marker_color=COLORS["blue"], marker_line_width=0))
        fig2.update_layout(title="DL Throughput by Site", **chart_layout())

        return html.Div([
            html.Div([
                card(dcc.Graph(figure=fig1, config={"displayModeBar": False}), style={"flex": 1}),
                card(dcc.Graph(figure=fig2, config={"displayModeBar": False}), style={"flex": 1}),
            ], style={"display": "flex", "gap": "12px"}),
            card(dash_table.DataTable(
                data=cdf.to_dict("records"),
                columns=[{"name": c, "id": c} for c in cdf.columns],
                style_table={"overflowX": "auto"},
                style_header={"background": COLORS["border"], "color": COLORS["text"],
                               "fontWeight": "500", "fontSize": "12px", "border": "none"},
                style_cell={"background": COLORS["bg"], "color": COLORS["text2"],
                             "fontSize": "12px", "border": f"1px solid {COLORS['border']}", "padding": "8px"},
                style_data_conditional=[
                    {"if": {"filter_query": "{CSR (%)} < 95"}, "color": COLORS["yellow"]},
                    {"if": {"filter_query": "{Anomalies} > 3"}, "color": COLORS["red"]},
                ],
            ))
        ])

    # ── AI ASSISTANT ──
    elif tab == "ai":
        return card([
            html.Div("AI Network Assistant", style={"fontWeight": "500", "fontSize": "16px", "marginBottom": "4px"}),
            html.Div("Ask anything about the network — KPIs, anomalies, fixes, or predictions.",
                     style={"fontSize": "13px", "color": COLORS["text2"], "marginBottom": "16px"}),
            html.Div([
                html.Div("Try asking:", style={"fontSize": "12px", "color": COLORS["text3"], "marginBottom": "8px"}),
                html.Div(["• Why did CSR drop at Chennai-N01 on Wednesday?  ",
                           "• What does PRB congestion mean?  ",
                           "• How do I fix a high drop rate?  ",
                           "• What is RSRP and why does it matter?"],
                         style={"fontSize": "12px", "color": COLORS["text2"], "lineHeight": "2",
                                "whiteSpace": "pre-line", "marginBottom": "16px"}),
            ]),
            html.Div(id="chat-history", style={"minHeight": "200px", "marginBottom": "12px"}),
            html.Div([
                dcc.Input(id="ai-input", type="text", placeholder="Type your question...",
                          debounce=False,
                          style={"flex": 1, "padding": "10px 14px", "borderRadius": "8px",
                                 "border": f"1px solid {COLORS['border']}", "background": COLORS["bg"],
                                 "color": COLORS["text"], "fontSize": "14px"}),
                html.Button("Ask AI", id="ai-btn", n_clicks=0,
                            style={"padding": "10px 20px", "background": "#a855f7", "color": "#fff",
                                   "border": "none", "borderRadius": "8px", "cursor": "pointer",
                                   "fontSize": "14px", "fontWeight": "500"})
            ], style={"display": "flex", "gap": "8px"}),
            html.Div(id="ai-loading", style={"fontSize": "12px", "color": COLORS["text3"], "marginTop": "8px"})
        ])

    return html.Div()

@app.callback(
    [Output("chat-history", "children"), Output("ai-loading", "children")],
    Input("ai-btn", "n_clicks"),
    [State("ai-input", "value"), State("chat-history", "children"),
     State("site-dd", "value"), State("tech-dd", "value"), State("day-dd", "value")],
    prevent_initial_call=True
)
def ask_ai(n_clicks, question, history, site, tech, day):
    if not question:
        return history, ""
    df = get_df(site, tech, day)
    anomalies = detect_anomalies(df)
    preds = predict_faults(df)

    context = f"""You are an expert telecom network engineer specializing in RAN (Radio Access Network) optimization.
Current dashboard state:
- Site: {site}, Technology: {tech}, Day: {day}
- Avg CSR: {df['csr'].mean():.1f}%, Avg DL: {df['throughput_dl'].mean():.0f} Mbps
- Peak PRB: {df['prb'].max():.1f}%, Avg RSRP: {df['rsrp'].mean():.1f} dBm
- Anomalies detected: {len(anomalies)}
- Predictions: {len(preds)} fault predictions

Anomaly details: {anomalies[:3] if anomalies else 'None'}
Predictions: {preds[:2] if preds else 'None'}

Answer the engineer's question clearly and concisely. Use simple language where possible but be technically accurate.
Reference the actual dashboard data in your answer when relevant."""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=context,
            messages=[{"role": "user", "content": question}]
        )
        answer = message.content[0].text
    except Exception as e:
        answer = f"AI unavailable: {str(e)}. Please check your ANTHROPIC_API_KEY."

    new_entry = html.Div([
        html.Div([
            html.Span("You", style={"fontWeight": "500", "color": "#a855f7"}),
            html.Div(question, style={"fontSize": "14px", "marginTop": "4px"})
        ], style={"background": COLORS["bg"], "borderRadius": "8px", "padding": "10px 14px",
                  "marginBottom": "8px", "borderLeft": "3px solid #a855f7"}),
        html.Div([
            html.Span("AI Engineer", style={"fontWeight": "500", "color": COLORS["green"]}),
            html.Div(answer, style={"fontSize": "14px", "marginTop": "4px", "lineHeight": "1.6"})
        ], style={"background": COLORS["bg"], "borderRadius": "8px", "padding": "10px 14px",
                  "marginBottom": "8px", "borderLeft": f"3px solid {COLORS['green']}"}),
    ])

    existing = history if isinstance(history, list) else ([history] if history else [])
    return existing + [new_entry], ""

def chart_layout():
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["text2"], size=11),
        margin=dict(l=40, r=20, t=40, b=30),
        xaxis=dict(gridcolor=COLORS["border"], showgrid=True),
        yaxis=dict(gridcolor=COLORS["border"], showgrid=True),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        height=280,
    )

# ─────────────────────────────────────────────
# 7. RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  RAN KPI Dashboard — Python + Dash")
    print("  Open your browser at: http://127.0.0.1:8050")
    print("="*50 + "\n")
    app.run(debug=True)
