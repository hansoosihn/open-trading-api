import argparse
from pathlib import Path
import sys

from .hts_core import fetch_real_quote, render_dashboard, serve_dashboard, simulate_quote


def dashboard_cmd(args: argparse.Namespace):
    symbol = args.symbol or "005930"
    output = Path(args.output or Path.cwd() / "dashboard.html")
    if args.real:
        quote = fetch_real_quote(symbol, environment=args.environment, product=args.product)
    else:
        quote = simulate_quote(symbol)
    data = {
        "quote": quote,
        "preview": {"symbol": symbol, "side": args.side},
        "environment": args.environment,
        "product": args.product,
        "generated_at": None,
    }
    out_path = render_dashboard(data, output)
    print(f"Wrote dashboard to: {out_path}")
    if args.serve:
        server, thread = serve_dashboard(out_path, host=args.host, port=args.port)
        print(f"Serving at http://{args.host}:{args.port}")
        try:
            thread.join()
        except KeyboardInterrupt:
            server.shutdown()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="hts-cli")
    sub = parser.add_subparsers(dest="command")
    dash = sub.add_parser("dashboard")
    dash.add_argument("symbol", nargs="?", help="종목코드", default="005930")
    dash.add_argument("--real", action="store_true", help="실데이터 사용")
    dash.add_argument("--output", help="출력 HTML 경로")
    dash.add_argument("--serve", action="store_true", help="로컬 서버로 제공")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8000)
    dash.add_argument("--environment", default="vps")
    dash.add_argument("--product", default="01")
    dash.add_argument("--side", default="BUY")

    args = parser.parse_args(argv)
    if args.command == "dashboard":
        dashboard_cmd(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
