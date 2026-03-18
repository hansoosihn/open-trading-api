# 한국투자증권 Home Trading System

이 폴더는 한국투자증권 Open API를 활용한 홈트레이딩 시스템의 시작점을 제공합니다.

## 구성 요소

- `hts_core.py`: 인증, 설정 로딩, 시세 시뮬레이션, 주문 미리보기 보조 함수
- `cli.py`: 터미널 기반 홈트레이딩 데모 CLI

## 사용 예시

```bash
python -m home_trading_system.cli quote 005930
python -m home_trading_system.cli order-preview 005930 BUY 10 75000
python -m home_trading_system.cli auth --env vps --product 01
python -m home_trading_system.cli dashboard 005930 --quantity 10 --price 75000 --output home_trading_system/output/dashboard.html --serve
```

`dashboard` 명령은 종목/주문 결과를 HTML 대시보드로 생성하고, `--serve` 옵션을 주면 로컬 서버로도 바로 확인할 수 있습니다.

## 고급 대시보드 입력

차트, 거래 내역, 포지션 데이터를 직접 전달해 더 풍부한 대시보드를 구성할 수 있습니다.

```bash
python -m home_trading_system.cli dashboard 005930 \
  --chart-data '{"series":[10000,10020,10015],"moving_average":[9995,10012,10018],"bands":[{"label":"지지선","value":9990,"color":"#22c55e"},{"label":"저항선","value":10030,"color":"#fb7185"}]}' \
  --trade-history '[{"time":"09:15","symbol":"005930","side":"BUY","quantity":5,"price":10000,"status":"체결","realized_pnl":120}]' \
  --positions '[{"symbol":"005930","side":"LONG","quantity":5,"avg_price":10000,"market_value":10050,"pnl":250,"pnl_rate":0.5,"status":"OPEN"}]' \
  --output home_trading_system/output/dashboard-rich.html
```

JSON 파일을 넘겨서 사용할 수도 있습니다.

```bash
python -m home_trading_system.cli dashboard 005930 \
  --chart-data ./chart_payload.json \
  --trade-history ./trade_history.json \
  --positions ./positions.json \
  --output home_trading_system/output/dashboard-rich.html
```

지원되는 입력 형식은 다음과 같습니다.

- `--chart-data`: `series`, `moving_average`, `bands`, `legend`를 포함한 객체 형태
- `--trade-history`: 거래 항목 배열 또는 `items`/`rows`를 포함한 객체 형태
- `--positions`: 포지션 항목 배열 또는 `items`/`rows`를 포함한 객체 형태

## 참고

- 기본 설정 파일 경로는 `~/KIS/config/kis_devlp.yaml`입니다.
- `KIS_CONFIG_PATH` 환경변수로 별도 경로를 지정할 수 있습니다.
- 실제 주문은 `dry_run=True` 미리보기 기준으로 제공되며, 실거래 연동을 위해 `order_cash` 등 API 래퍼를 추가할 수 있습니다.
