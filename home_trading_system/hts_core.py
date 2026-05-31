import html
import os
import sys
import threading
import math
from dataclasses import dataclass, field
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class HtsSession:
    environment: str
    product: str
    config: Dict[str, Any] = field(default_factory=dict)
    authenticated: bool = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_repo_on_path() -> None:
    repo_root = str(_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _resolve_config_path(config_path: Optional[str | Path]) -> Path:
    if config_path is not None:
        path = Path(config_path).expanduser()
    else:
        env_path = os.getenv("KIS_CONFIG_PATH")
        if env_path:
            path = Path(env_path).expanduser()
        else:
            path = Path.home() / "KIS" / "config" / "kis_devlp.yaml"
    return path


def load_config(config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    path = _resolve_config_path(config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


_KNOWN_SYMBOL_NAMES = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "005380": "현대차",
}


def _resolve_symbol_name(symbol: str, fallback: Optional[str] = None) -> str:
    symbol = str(symbol).strip()
    if fallback:
        name = str(fallback).strip()
        if name:
            return name
    return _KNOWN_SYMBOL_NAMES.get(symbol) or symbol


def simulate_quote(symbol: str) -> Dict[str, Any]:
    symbol = str(symbol).strip()
    price_map = {"005930": 74700, "000660": 112500, "035420": 65000}
    base_price = price_map.get(symbol, 10000)
    fingerprint = sum(bytearray(symbol.encode("utf-8")))
    variation = ((fingerprint % 10) - 4.5) / 100.0
    price = round(base_price * (1 + variation), 2)
    return {
        "symbol": symbol,
        "name": _resolve_symbol_name(symbol),
        "price": price,
        "currency": "KRW",
        "market": "KOSPI",
        "source": "demo-simulator",
    }


def _load_stock_functions():
    _ensure_repo_on_path()
    try:
        import importlib
        return importlib.import_module("examples_user.domestic_stock.domestic_stock_functions")
    except Exception:
        raise


def authenticate(environment: str = "vps", product: str = "01", config_path: Optional[str | Path] = None) -> HtsSession:
    _ensure_repo_on_path()
    config = load_config(config_path)
    try:
        import examples_user.kis_auth as ka
        ka.auth(svr=environment, product=product)
    except Exception:
        # best-effort: continue if auth helpers not available
        pass
    return HtsSession(environment=environment, product=product, config=config, authenticated=True)


def fetch_real_quote(symbol: str, environment: str = "vps", product: str = "01", config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    symbol = str(symbol).strip()
    if not symbol:
        raise ValueError("symbol required")
    authenticate(environment=environment, product=product, config_path=config_path)
    env_dv = "demo" if str(environment).lower() == "vps" else "real"
    try:
        stock_functions = _load_stock_functions()
        df = stock_functions.inquire_price(env_dv=env_dv, fid_cond_mrkt_div_code="J", fid_input_iscd=symbol)
        if df is None or df.empty:
            return simulate_quote(symbol)
        row = df.iloc[0]
        price = _to_float(row.get("stck_prpr")) or _to_float(row.get("stck_sdpr")) or 0
        quote = {
            "symbol": str(row.get("stck_shrn_iscd") or symbol),
            "name": _resolve_symbol_name(str(row.get("stck_shrn_iscd") or symbol), str(row.get("stck_kor_isnm") or row.get("stck_kor_isnm") or row.get("bstp_kor_isnm") or "")),
            "price": round(price, 2),
            "currency": "KRW",
            "market": str(row.get("rprs_mrkt_kor_name") or "KOSPI"),
            "source": f"{env_dv}-api",
            "sector": str(row.get("bstp_kor_isnm") or ""),
            "open_price": _to_float(row.get("stck_oprc")),
            "high_price": _to_float(row.get("stck_hgpr")),
            "low_price": _to_float(row.get("stck_lwpr")),
            "volume": row.get("acml_vol"),
            "change": _to_float(row.get("prdy_vrss")),
            "change_rate": _to_float(row.get("prdy_ctrt")),
        }
        return quote
    except Exception:
        return simulate_quote(symbol)


def _normalize_trade_history(raw_history: Optional[list[Dict[str, Any]]], symbol: str, reference_price: float) -> list[Dict[str, Any]]:
    if isinstance(raw_history, dict):
        raw_history = raw_history.get("items") or raw_history.get("rows") or list(raw_history.values())
    if raw_history:
        normalized = []
        for entry in raw_history:
            if not isinstance(entry, dict):
                continue
            normalized_entry = dict(entry)
            normalized_entry["symbol"] = str(normalized_entry.get("symbol") or symbol)
            normalized_entry["name"] = str(normalized_entry.get("name") or _resolve_symbol_name(normalized_entry["symbol"]))
            normalized_entry["side"] = str(normalized_entry.get("side") or "UNKNOWN")
            normalized_entry["quantity"] = int(normalized_entry.get("quantity") or 0)
            normalized_entry["price"] = float(normalized_entry.get("price") or reference_price)
            normalized_entry["status"] = str(normalized_entry.get("status") or "UNKNOWN")
            normalized.append(normalized_entry)
        return normalized
    base_price = float(reference_price or 10000)
    history = [
        {"time": "09:20", "side": "BUY", "quantity": 10, "price": round(base_price * 0.995, 2), "status": "체결", "realized_pnl": 0},
        {"time": "10:10", "side": "SELL", "quantity": 5, "price": round(base_price * 1.012, 2), "status": "체결", "realized_pnl": 2400},
        {"time": "11:05", "side": "BUY", "quantity": 5, "price": round(base_price * 1.006, 2), "status": "대기", "realized_pnl": 0},
    ]
    for entry in history:
        entry["symbol"] = symbol
        entry["name"] = _resolve_symbol_name(symbol)
    return history


def _normalize_positions(raw_positions: Optional[list[Dict[str, Any]]], symbol: str, reference_price: float) -> list[Dict[str, Any]]:
    if isinstance(raw_positions, dict):
        raw_positions = raw_positions.get("items") or raw_positions.get("rows") or list(raw_positions.values())
    if raw_positions:
        normalized = []
        for position in raw_positions:
            if not isinstance(position, dict):
                continue
            normalized_position = dict(position)
            normalized_position["symbol"] = str(normalized_position.get("symbol") or symbol)
            normalized_position["name"] = str(normalized_position.get("name") or _resolve_symbol_name(normalized_position["symbol"]))
            normalized_position["side"] = str(normalized_position.get("side") or "LONG")
            normalized_position["quantity"] = int(normalized_position.get("quantity") or 0)
            normalized_position["avg_price"] = float(normalized_position.get("avg_price") or reference_price)
            normalized_position["market_value"] = float(normalized_position.get("market_value") or (normalized_position["avg_price"] * normalized_position["quantity"]))
            normalized_position["pnl"] = float(normalized_position.get("pnl") or (normalized_position["market_value"] - normalized_position["avg_price"] * normalized_position["quantity"]))
            normalized_position["pnl_rate"] = float(normalized_position.get("pnl_rate") or 0)
            normalized_position["status"] = str(normalized_position.get("status") or "OPEN")
            normalized.append(normalized_position)
        return normalized
    market_value = round(reference_price * 10, 2)
    unrealized = round(market_value * 0.012, 2)
    return [{
        "symbol": symbol,
        "name": _resolve_symbol_name(symbol),
        "side": "LONG",
        "quantity": 10,
        "avg_price": round(reference_price, 2),
        "market_value": market_value,
        "pnl": unrealized,
        "pnl_rate": 1.2,
        "status": "OPEN",
    }]


def _format_symbol_label(symbol: str, name: Optional[str] = None) -> str:
    symbol = str(symbol).strip()
    display_name = str(name or "").strip()
    resolved_name = _resolve_symbol_name(symbol, display_name)
    if resolved_name and resolved_name != symbol:
        return f"{symbol} · {resolved_name}"
    return symbol


def _dashboard_card(title: str, value: str, accent: str = "blue", field_id: Optional[str] = None) -> str:
    field_attrs = f' id="{html.escape(field_id)}"' if field_id else ""
    return f"""
    <div class="metric-card metric-{accent}"{field_attrs}>
        <div class="metric-label">{html.escape(title)}</div>
        <div class="metric-value">{html.escape(str(value))}</div>
    </div>
    """


def _render_svg_chart(chart_payload: Dict[str, Any]) -> str:
    series = chart_payload.get("series") or []
    width = 680
    height = 160
    pad_x = 36
    pad_y = 18
    if not series:
        return "<div class=\"mini-chart\">No chart data</div>"
    min_value = min(series)
    max_value = max(series)
    span = max(1.0, max_value - min_value)
    points = []
    step = (width - pad_x * 2) / max(1, (len(series) - 1))
    for i, v in enumerate(series):
        x = pad_x + i * step
        y = height - pad_y - ((v - min_value) / span) * (height - pad_y * 2)
        points.append(f"{x:.1f},{y:.1f}")
    path = " ".join(points)
    return f"<svg viewBox=\"0 0 {width} {height}\" class=\"mini-chart\">" + f"<polyline points=\"{path}\" fill=\"none\" stroke=\"#2dd4bf\" stroke-width=2/>" + "</svg>"


def render_dashboard(data: Dict[str, Any], output_path: Optional[str | Path] = None) -> Path:
    output_path = Path(output_path or Path.cwd() / "dashboard.html").expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    quote = data.get("quote") or {}
    preview = data.get("preview") or {}
    session = data.get("session") or {}
    generated_at = data.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    symbol = str(quote.get("symbol") or preview.get("symbol") or "UNKNOWN")
    stock_name = str(quote.get("name") or _resolve_symbol_name(symbol))
    display_symbol = _format_symbol_label(symbol, stock_name)
    current_price = float(quote.get("price") or 0)

    chart_payload = {"series": data.get("chart_data", {}).get("series") if isinstance(data.get("chart_data"), dict) else None} or {"series": [current_price]}
    trade_history = _normalize_trade_history(data.get("trade_history"), symbol, current_price)
    positions = _normalize_positions(data.get("positions"), symbol, current_price)

    summary_cards = [
        _dashboard_card("환경", session.get("environment") or data.get("environment") or "unknown"),
        _dashboard_card("계좌상품", session.get("product") or data.get("product") or "unknown"),
        _dashboard_card("종목코드", display_symbol, field_id="symbol-code-card"),
        _dashboard_card("현재가", f"{current_price:,.0f} KRW", field_id="price-card"),
        _dashboard_card("주문방향", preview.get("side") or "-"),
    ]

    chart_html = _render_svg_chart(chart_payload)

    trade_rows = "".join(
        f"""
        <tr>
            <td>{html.escape(str(entry.get('time')))}</td>
            <td>{html.escape(_format_symbol_label(str(entry.get('symbol')), str(entry.get('name'))))}</td>
            <td>{html.escape(str(entry.get('side')))}</td>
            <td>{entry.get('quantity', 0)}</td>
            <td>{float(entry.get('price', 0)):,.0f}</td>
            <td>{html.escape(str(entry.get('status')))}</td>
            <td>{float(entry.get('realized_pnl', 0)):,.0f}</td>
        </tr>
        """
        for entry in trade_history
    )

    position_rows = "".join(
        f"""
        <tr>
            <td>{html.escape(_format_symbol_label(str(position.get('symbol')), str(position.get('name'))))}</td>
            <td>{html.escape(str(position.get('side')))}</td>
            <td>{position.get('quantity', 0)}</td>
            <td>{float(position.get('avg_price', 0)):,.0f}</td>
            <td>{float(position.get('market_value', 0)):,.0f}</td>
            <td>{float(position.get('pnl', 0)):,.0f}</td>
            <td>{html.escape(str(position.get('status')))}</td>
            <td>{float(position.get('pnl_rate', 0)):.1f}%</td>
        </tr>
        """
        for position in positions
    )

    html_template = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Home Trading Dashboard</title>
    <style>
        :root {{ --bg:#040b1f; --text-main:#f7f7fb; --text-muted:#9ca8c8; --accent:#2dd4bf; --shadow:0 28px 90px rgba(0,0,0,0.35); }}
        body {{ background:linear-gradient(180deg,#020817,#01040d 30%,#000 100%); color:var(--text-main); font-family:Inter,system-ui,sans-serif; margin:0; }}
        .shell {{ padding:20px; }}
        .card-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:12px 0; }}
        .metric-card {{ background:rgba(8,16,34,0.86); padding:14px; border-radius:12px; border:1px solid rgba(84,110,190,0.24); }}
        .metric-label {{ color:var(--text-muted); font-size:12px; text-transform:uppercase; }}
        .metric-value {{ margin-top:8px; font-size:1.2rem; font-weight:700; }}
        .symbol-toolbar {{ margin:8px 0 14px; display:flex; gap:10px; align-items:center; }}
        .symbol-input {{ padding:8px 10px; border-radius:999px; border:1px solid rgba(96,165,250,0.2); background:rgba(2,8,24,0.9); color:var(--text-main); min-width:140px; }}
        .symbol-button {{ padding:8px 12px; border-radius:999px; border:none; background:linear-gradient(180deg,#2dd4bf,#60a5fa); color:#02111f; font-weight:700; cursor:pointer; }}
        table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
        th,td{{ text-align:left; padding:8px 10px; border-bottom:1px solid rgba(84,110,190,0.12); font-size:13px; }}
    </style>
</head>
<body>
    <div class="shell">
        <h1>Home Trading Dashboard</h1>
        <div class="symbol-toolbar">
            <form id="symbol-form"><input id="dashboard-symbol-input" class="symbol-input" value="{html.escape(symbol)}"/><button class="symbol-button" type="submit">조회</button></form>
        </div>
        <section class="card-grid">{''.join(summary_cards)}</section>
        <section>
            <h2>가격 추이</h2>
            <div class="summary-inline"><span id="chart-symbol-summary">종목: {html.escape(display_symbol)}</span> <span id="chart-price-summary">현재가: {current_price:,.0f} KRW</span></div>
            __CHART_HTML__
        </section>

        <section>
            <h2>거래 내역</h2>
            <table>
                <thead><tr><th>시간</th><th>종목</th><th>방향</th><th>수량</th><th>가격</th><th>상태</th><th>실현손익</th></tr></thead>
                <tbody>__TRADE_ROWS__</tbody>
            </table>
        </section>

        <section>
            <h2>포지션 상태</h2>
            <table>
                <thead><tr><th>종목</th><th>방향</th><th>수량</th><th>평균가</th><th>시장가치</th><th>P/L</th><th>상태</th><th>P/L%</th></tr></thead>
                <tbody>__POSITION_ROWS__</tbody>
            </table>
        </section>

        <div class="footer">생성 시각: __GEN_AT__ · HTML 대시보드</div>
    </div>
    <script>
        (function(){
            const symbolNameMap = {"005930":"삼성전자","000660":"SK하이닉스","035420":"NAVER","035720":"카카오","005380":"현대차"};
            const basePriceMap = {"005930":74700,"000660":112500,"035420":65000,"035720":58000,"005380":96500};
            const fmt = new Intl.NumberFormat('ko-KR');
            const symbolInput = document.getElementById('dashboard-symbol-input');
            const symbolForm = document.getElementById('symbol-form');
            const symbolCodeCard = document.getElementById('symbol-code-card');
            const priceCard = document.getElementById('price-card');
            const chartSymbolSummary = document.getElementById('chart-symbol-summary');
            const chartPriceSummary = document.getElementById('chart-price-summary');
            const fallbackPrice = (s)=>{const seed=s.split('').reduce((a,c)=>a+c.charCodeAt(0),0);return 10000+(seed%6000)*10};
            const formatDisplay=(s)=>{const n=String(s).toUpperCase();const name=symbolNameMap[n]||n;return `${n} · ${name}`};
            const updateDashboard=(raw)=>{const n=String(raw||'').trim().toUpperCase();if(!n)return;const price=basePriceMap[n]||fallbackPrice(n);const display=formatDisplay(n);if(symbolCodeCard){const v=symbolCodeCard.querySelector('.metric-value');if(v)v.textContent=display;}if(priceCard){const v=priceCard.querySelector('.metric-value');if(v)v.textContent=`${fmt.format(price)} KRW`}if(chartSymbolSummary)chartSymbolSummary.textContent=`종목: ${display}`;if(chartPriceSummary)chartPriceSummary.textContent=`현재가: ${fmt.format(price)} KRW`;try{history.replaceState(null,'',`?symbol=${encodeURIComponent(n)}`)}catch(e){}if(symbolInput)symbolInput.value=n};
            if(symbolForm)symbolForm.addEventListener('submit',(e)=>{e.preventDefault();updateDashboard(symbolInput.value)});
            const p=new URLSearchParams(window.location.search);const init=p.get('symbol');if(init)updateDashboard(init);
        })();
    </script>
</body>
</html>
"""

    html_content = html_template.replace('__SYMBOL__', html.escape(symbol))
    html_content = html_content.replace('__DISPLAY_SYMBOL__', html.escape(display_symbol))
    html_content = html_content.replace('__CURRENT_PRICE__', f"{current_price:,.0f} KRW")
    html_content = html_content.replace('__CHART_HTML__', chart_html)
    html_content = html_content.replace('__TRADE_ROWS__', trade_rows)
    html_content = html_content.replace('__POSITION_ROWS__', position_rows)
    html_content = html_content.replace('__GEN_AT__', html.escape(generated_at))

    output_path.write_text(html_content, encoding="utf-8")
    return output_path


def serve_dashboard(output_path: Path, host: str = "127.0.0.1", port: int = 8000):
    output_path = Path(output_path).expanduser()
    if not output_path.exists():
        raise FileNotFoundError(f"Dashboard not found: {output_path}")

    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(output_path.parent), **kwargs)

        def do_GET(self):
            if self.path in ('/', ''):
                self.path = '/' + output_path.name
            return super().do_GET()

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def save_keys_to_file(access_token: str, approval_key: str, path: Optional[str | Path] = None) -> Path:
    """Persist `access_token` and `approval_key` to a YAML file.

    Returns the written Path.
    """
    target = Path(path or (Path.home() / ".kis_tokens.yaml")).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": access_token,
        "approval_key": approval_key,
        "created_at": datetime.utcnow().isoformat(),
    }
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target


def obtain_and_save_keys(environment: str = "vps", product: str = "01", out_path: Optional[str | Path] = None) -> Path:
    """Attempt to obtain access/approval keys via `examples_user.kis_auth` helpers and save them.

    This function tries several common helper names in `kis_auth`. If it cannot
    automatically obtain tokens it raises RuntimeError with diagnostic info.
    """
    _ensure_repo_on_path()
    try:
        import examples_user.kis_auth as ka
    except Exception as exc:
        raise RuntimeError("examples_user.kis_auth not importable") from exc

    tokens = None
    # try common helper names that may return tokens
    candidate_names = [
        "issue_tokens",
        "issue_access_token",
        "get_tokens",
        "get_access_and_approval",
        "request_token",
        "auth_and_get_tokens",
    ]
    for name in candidate_names:
        fn = getattr(ka, name, None)
        if not fn:
            continue
        try:
            # prefer keyword form
            tokens = fn(svr=environment, product=product)
        except TypeError:
            try:
                tokens = fn(environment, product)
            except Exception:
                continue
        except Exception:
            continue
        if tokens:
            break

    # fallback: call auth() then attempt to read token / approval via known helpers
    if not tokens:
        try:
            if hasattr(ka, "auth"):
                ka.auth(svr=("prod" if environment == "prod" else "vps"), product=product)
        except Exception:
            pass

        # try read_token() which returns a token string
        try:
            access_read = getattr(ka, "read_token", None)
            access_val = access_read() if callable(access_read) else None
        except Exception:
            access_val = None

        # try to obtain approval_key via auth_ws()
        try:
            if hasattr(ka, "auth_ws"):
                ka.auth_ws(svr=("prod" if environment == "prod" else "vps"), product=product)
            approval_val = None
            if hasattr(ka, "_base_headers_ws"):
                approval_val = ka._base_headers_ws.get("approval_key")
        except Exception:
            approval_val = None

        access = access_val
        approval = approval_val

    else:
        access = tokens.get("access_token") or tokens.get("access") or tokens.get("token")
        approval = tokens.get("approval_key") or tokens.get("approval") or tokens.get("approvalKey")

    if not access or not approval:
        available = ", ".join([n for n in dir(ka) if not n.startswith("_")][:100])
        raise RuntimeError(f"Could not obtain both tokens. available kis_auth members: {available}")

    return save_keys_to_file(access, approval, out_path)
