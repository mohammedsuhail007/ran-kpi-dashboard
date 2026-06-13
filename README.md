# RAN KPI Dashboard 📡

A Python-based Radio Access Network (RAN) KPI monitoring dashboard built with Dash and Plotly. Designed to simulate real-world Network Design & Optimisation (NDO) workflows across 2G, 3G, 4G, and 5G technologies.

## Features

- **Real-time KPI Monitoring** — Track Call Setup Success Rate, DL Throughput, PRB Utilization, RSRP, and Drop Rate across 5 cell sites
- **Anomaly Detection** — Automatically flags degradations using statistical threshold analysis
- **Predictive Fault Detection** — Predicts network faults before they happen using KPI trend analysis
- **Alarm Management** — Full alarm log with severity classification (CRITICAL/WARNING) and status tracking
- **Site Comparison** — Compare KPI performance across multiple cities simultaneously
- **AI Assistant** — Natural language interface powered by Claude API for root cause analysis

## Technologies Used

- Python 3.13
- Dash & Plotly — Interactive dashboard and charts
- Pandas — Data processing and analysis
- Anthropic Claude API — AI-powered network assistant

## KPIs Monitored

| KPI | Description | Threshold |
|-----|-------------|-----------|
| Call Setup Success Rate (CSR) | % of calls successfully connected | > 95% |
| DL Throughput | Download speed per site | 5G: 400 Mbps |
| PRB Utilization | Radio resource usage | < 90% |
| RSRP | Signal strength | > -85 dBm |
| Drop Rate | % of calls disconnected | < 1% |

## How to Run

```bash
pip install dash plotly pandas anthropic
python app.py
```

Open browser at `http://127.0.0.1:8050`

## Project Structure
ran-kpi-dashboard/
│
├── app.py          # Main dashboard application
└── README.md       # Project documentation
## Screenshots

Dashboard covers 5 sites across Chennai, Mumbai, Delhi and Bangalore with 7-day historical data and 24-hour hourly resolution.

## Author

Built as part of a Network Design & Optimisation portfolio project targeting telecom engineering roles.
