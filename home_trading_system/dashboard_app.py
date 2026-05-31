#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AutoStock HTS desktop application.

This is a broker-style desktop shell for monitoring quotes, clicking an order
book price, reviewing account state, and tracking order logs. The default mode
is a safe demo mode so the UI can be used even when the broker API is not
available.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "examples_user") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "examples_user"))


try:
    import kis_auth as ka  # type: ignore
    from examples_user.domestic_stock import domestic_stock_functions as dsf  # type: ignore
except Exception:
    ka = None
    dsf = None


@dataclass
class StockState:
    code: str
    name: str
    price: int
    previous_close: int
    open_price: int
    high_price: int
    low_price: int
    volume: int = 0
    history: List[int] = field(default_factory=list)

    @property
    def change(self) -> int:
        return self.price - self.previous_close

    @property
    def change_rate(self) -> float:
        if self.previous_close <= 0:
            return 0.0
        return self.change / self.previous_close * 100


class HtsColors:
    BG = "#111827"
    PANEL = "#172033"
    PANEL_2 = "#1f2937"
    GRID = "#374151"
    TEXT = "#e5e7eb"
    MUTED = "#9ca3af"
    BUY = "#ef4444"
    SELL = "#3b82f6"
    GREEN = "#22c55e"
    WARN = "#f59e0b"


class AutoStockHts(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoStock HTS")
        self.resize(1480, 920)

        self.account_no = self._load_account_no()
        self.cash = 50_000_000
        self.order_seq = 1
        self.live_updates = True
        self.active_code = "005930"
        self.orders: List[Dict[str, str]] = []
        self.positions: Dict[str, Dict[str, int | str]] = {
            "005930": {"name": "삼성전자", "qty": 12, "avg": 74200},
            "035420": {"name": "NAVER", "qty": 8, "avg": 183000},
        }
        self.stocks = self._create_default_stocks()

        self._apply_theme()
        self._build_ui()
        self._wire_events()
        self._refresh_all()

        self.market_timer = QTimer(self)
        self.market_timer.timeout.connect(self._tick_market)
        self.market_timer.start(1200)
        self.log("시스템", "AutoStock HTS 데모 모드 시작")

    def _load_account_no(self) -> str:
        if ka is None:
            return "DEMO-00000000"
        try:
            cfg = ka.getEnv()
            return str(cfg.get("my_paper_stock", "DEMO-00000000"))[:8]
        except Exception:
            return "DEMO-00000000"

    def _create_default_stocks(self) -> Dict[str, StockState]:
        seed = {
            "005930": ("삼성전자", 74700),
            "000660": ("SK하이닉스", 210500),
            "035420": ("NAVER", 183000),
            "035720": ("카카오", 43600),
            "005380": ("현대차", 256000),
            "068270": ("셀트리온", 181500),
            "051910": ("LG화학", 346000),
            "207940": ("삼성바이오로직스", 894000),
        }
        stocks: Dict[str, StockState] = {}
        for code, (name, price) in seed.items():
            previous = int(price * random.uniform(0.985, 1.015))
            stocks[code] = StockState(
                code=code,
                name=name,
                price=price,
                previous_close=previous,
                open_price=previous,
                high_price=max(price, previous),
                low_price=min(price, previous),
                volume=random.randint(100_000, 2_000_000),
                history=[previous, price],
            )
        return stocks

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: {HtsColors.BG};
                color: {HtsColors.TEXT};
                font-family: Malgun Gothic, Segoe UI, Arial;
                font-size: 10pt;
            }}
            QGroupBox {{
                background: {HtsColors.PANEL};
                border: 1px solid {HtsColors.GRID};
                border-radius: 6px;
                margin-top: 9px;
                padding: 8px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QTableWidget {{
                background: {HtsColors.PANEL_2};
                color: {HtsColors.TEXT};
                gridline-color: {HtsColors.GRID};
                selection-background-color: #334155;
                selection-color: #ffffff;
                border: 1px solid {HtsColors.GRID};
            }}
            QHeaderView::section {{
                background: #0f172a;
                color: {HtsColors.TEXT};
                border: 1px solid {HtsColors.GRID};
                padding: 4px;
                font-weight: 600;
            }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
                background: #0f172a;
                color: {HtsColors.TEXT};
                border: 1px solid {HtsColors.GRID};
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton {{
                background: #334155;
                color: #ffffff;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 8px;
            }}
            QPushButton:hover {{ background: #475569; }}
            QToolBar {{
                background: #0f172a;
                border-bottom: 1px solid {HtsColors.GRID};
                spacing: 8px;
                padding: 5px;
            }}
            QTabWidget::pane {{
                border: 1px solid {HtsColors.GRID};
                background: {HtsColors.PANEL};
            }}
            QTabBar::tab {{
                background: #0f172a;
                color: {HtsColors.MUTED};
                padding: 8px 14px;
                border: 1px solid {HtsColors.GRID};
            }}
            QTabBar::tab:selected {{
                background: {HtsColors.PANEL_2};
                color: #ffffff;
            }}
            """
        )

    def _build_ui(self) -> None:
        self._build_toolbar()
        self.setStatusBar(QStatusBar(self))

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)

        self.market_strip = QLabel()
        self.market_strip.setFrameShape(QFrame.StyledPanel)
        self.market_strip.setStyleSheet(
            "background:#0f172a; border:1px solid #374151; padding:6px;"
        )
        root_layout.addWidget(self.market_strip)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(self._build_left_panel())
        main_splitter.addWidget(self._build_center_panel())
        main_splitter.addWidget(self._build_right_panel())
        main_splitter.setSizes([310, 770, 380])
        root_layout.addWidget(main_splitter, 1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(130)
        root_layout.addWidget(self.log_box)

        self.setCentralWidget(root)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        title = QLabel("  AutoStock HTS  ")
        title.setFont(QFont("Malgun Gothic", 13, QFont.Bold))
        toolbar.addWidget(title)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("계좌 "))
        self.account_label = QLabel(self.account_no)
        self.account_label.setStyleSheet("color:#bfdbfe; font-weight:bold;")
        toolbar.addWidget(self.account_label)
        toolbar.addWidget(QLabel("  예수금 "))
        self.cash_label = QLabel("-")
        self.cash_label.setStyleSheet("color:#86efac; font-weight:bold;")
        toolbar.addWidget(self.cash_label)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("환경 "))
        self.env_combo = QComboBox()
        self.env_combo.addItems(["demo", "vps", "prod"])
        self.env_combo.setCurrentText("demo")
        toolbar.addWidget(self.env_combo)

        self.start_btn = QPushButton("실시간 ON")
        self.stop_btn = QPushButton("실시간 OFF")
        toolbar.addWidget(self.start_btn)
        toolbar.addWidget(self.stop_btn)

        toolbar.addSeparator()
        self.clock_label = QLabel()
        toolbar.addWidget(self.clock_label)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        search_group = QGroupBox("종목 검색")
        search_layout = QGridLayout(search_group)
        self.symbol_input = QLineEdit(self.active_code)
        self.symbol_input.setPlaceholderText("종목코드 예: 005930")
        self.search_btn = QPushButton("조회/추가")
        search_layout.addWidget(QLabel("코드"), 0, 0)
        search_layout.addWidget(self.symbol_input, 0, 1)
        search_layout.addWidget(self.search_btn, 0, 2)
        layout.addWidget(search_group)

        watch_group = QGroupBox("관심종목")
        watch_layout = QVBoxLayout(watch_group)
        self.watch_table = QTableWidget(0, 6)
        self.watch_table.setHorizontalHeaderLabels(["코드", "종목명", "현재가", "대비", "등락률", "거래량"])
        self.watch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.watch_table.verticalHeader().setVisible(False)
        self.watch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.watch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        watch_layout.addWidget(self.watch_table)
        layout.addWidget(watch_group, 1)

        news_group = QGroupBox("뉴스/알림")
        news_layout = QVBoxLayout(news_group)
        self.news_box = QTextEdit()
        self.news_box.setReadOnly(True)
        self.news_box.setText(
            "09:00 장 시작\n09:05 삼성전자 외국인 순매수 유입\n"
            "09:12 반도체 업종 강세\n09:30 데모 모드: 주문은 실제 전송되지 않음"
        )
        news_layout.addWidget(self.news_box)
        layout.addWidget(news_group)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        quote_group = QGroupBox("현재 종목")
        quote_layout = QGridLayout(quote_group)
        self.quote_name = QLabel()
        self.quote_name.setFont(QFont("Malgun Gothic", 18, QFont.Bold))
        self.quote_price = QLabel()
        self.quote_price.setFont(QFont("Consolas", 24, QFont.Bold))
        self.quote_change = QLabel()
        self.quote_ohlv = QLabel()
        quote_layout.addWidget(self.quote_name, 0, 0)
        quote_layout.addWidget(self.quote_price, 0, 1, Qt.AlignRight)
        quote_layout.addWidget(self.quote_change, 1, 0)
        quote_layout.addWidget(self.quote_ohlv, 1, 1, Qt.AlignRight)
        layout.addWidget(quote_group)

        tabs = QTabWidget()
        tabs.addTab(self._build_order_book_tab(), "호가/주문")
        tabs.addTab(self._build_chart_tab(), "차트")
        tabs.addTab(self._build_orders_tab(), "주문/체결")
        layout.addWidget(tabs, 1)
        return panel

    def _build_order_book_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.order_book_table = QTableWidget(20, 5)
        self.order_book_table.setHorizontalHeaderLabels(
            ["매도주문", "매도잔량", "호가", "매수잔량", "매수주문"]
        )
        self.order_book_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_book_table.verticalHeader().setVisible(False)
        self.order_book_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.order_book_table, 2)

        detail = QGroupBox("종목 상세")
        detail_layout = QGridLayout(detail)
        self.detail_labels: Dict[str, QLabel] = {}
        for row, key in enumerate(["시가", "고가", "저가", "전일종가", "거래량", "주문가능"]):
            detail_layout.addWidget(QLabel(key), row, 0)
            self.detail_labels[key] = QLabel("-")
            self.detail_labels[key].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            detail_layout.addWidget(self.detail_labels[key], row, 1)
        layout.addWidget(detail, 1)
        return widget

    def _build_chart_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.chart_table = QTableWidget(0, 2)
        self.chart_table.setHorizontalHeaderLabels(["Tick", "Price"])
        self.chart_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.chart_table.verticalHeader().setVisible(False)
        layout.addWidget(QLabel("간이 틱 차트 데이터"))
        layout.addWidget(self.chart_table)
        return widget

    def _build_orders_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(
            ["시간", "주문번호", "종목", "구분", "수량", "가격", "상태", "환경"]
        )
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.orders_table)
        return widget

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_order_ticket())
        layout.addWidget(self._build_account_panel())
        return panel

    def _build_order_ticket(self) -> QGroupBox:
        group = QGroupBox("주문 입력")
        layout = QGridLayout(group)

        self.ticket_code = QLineEdit(self.active_code)
        self.ticket_name = QLabel()
        self.side_combo = QComboBox()
        self.side_combo.addItems(["매수", "매도"])
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 1_000_000)
        self.qty_spin.setValue(10)
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(1, 100_000_000)
        self.price_spin.setDecimals(0)
        self.price_spin.setSingleStep(100)
        self.order_type = QComboBox()
        self.order_type.addItems(["지정가", "시장가"])

        layout.addWidget(QLabel("종목"), 0, 0)
        layout.addWidget(self.ticket_code, 0, 1)
        layout.addWidget(self.ticket_name, 0, 2)
        layout.addWidget(QLabel("구분"), 1, 0)
        layout.addWidget(self.side_combo, 1, 1, 1, 2)
        layout.addWidget(QLabel("수량"), 2, 0)
        layout.addWidget(self.qty_spin, 2, 1, 1, 2)
        layout.addWidget(QLabel("가격"), 3, 0)
        layout.addWidget(self.price_spin, 3, 1, 1, 2)
        layout.addWidget(QLabel("유형"), 4, 0)
        layout.addWidget(self.order_type, 4, 1, 1, 2)

        self.buy_btn = QPushButton("매수 주문")
        self.buy_btn.setStyleSheet(f"background:{HtsColors.BUY}; font-weight:bold;")
        self.sell_btn = QPushButton("매도 주문")
        self.sell_btn.setStyleSheet(f"background:{HtsColors.SELL}; font-weight:bold;")
        self.cancel_btn = QPushButton("입력 초기화")
        layout.addWidget(self.buy_btn, 5, 0, 1, 3)
        layout.addWidget(self.sell_btn, 6, 0, 1, 3)
        layout.addWidget(self.cancel_btn, 7, 0, 1, 3)
        return group

    def _build_account_panel(self) -> QGroupBox:
        group = QGroupBox("계좌/잔고")
        layout = QVBoxLayout(group)

        self.account_summary = QLabel()
        self.account_summary.setStyleSheet("font-size:12pt; font-weight:bold;")
        layout.addWidget(self.account_summary)

        self.portfolio_table = QTableWidget(0, 6)
        self.portfolio_table.setHorizontalHeaderLabels(["종목", "수량", "평균가", "현재가", "평가금액", "손익"])
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.portfolio_table.verticalHeader().setVisible(False)
        self.portfolio_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.portfolio_table, 1)
        return group

    def _wire_events(self) -> None:
        self.start_btn.clicked.connect(self._start_updates)
        self.stop_btn.clicked.connect(self._stop_updates)
        self.search_btn.clicked.connect(self._search_or_add_symbol)
        self.watch_table.itemSelectionChanged.connect(self._select_watch_symbol)
        self.buy_btn.clicked.connect(lambda: self._submit_ticket("매수"))
        self.sell_btn.clicked.connect(lambda: self._submit_ticket("매도"))
        self.cancel_btn.clicked.connect(self._reset_ticket)
        self.ticket_code.returnPressed.connect(self._apply_ticket_symbol)

    def _start_updates(self) -> None:
        self.live_updates = True
        self.statusBar().showMessage("실시간 업데이트 ON", 3000)
        self.log("시스템", "실시간 업데이트 ON")

    def _stop_updates(self) -> None:
        self.live_updates = False
        self.statusBar().showMessage("실시간 업데이트 OFF", 3000)
        self.log("시스템", "실시간 업데이트 OFF")

    def _search_or_add_symbol(self) -> None:
        code = self.symbol_input.text().strip().upper()
        if not code:
            return
        if code not in self.stocks:
            base = random.randint(8_000, 300_000)
            self.stocks[code] = StockState(
                code=code,
                name=f"종목{code}",
                price=base,
                previous_close=base,
                open_price=base,
                high_price=base,
                low_price=base,
                volume=0,
                history=[base],
            )
            self.log("관심종목", f"{code} 추가")
        self._set_active_symbol(code)
        self._refresh_all()

    def _select_watch_symbol(self) -> None:
        row = self.watch_table.currentRow()
        if row < 0:
            return
        item = self.watch_table.item(row, 0)
        if item:
            self._set_active_symbol(item.text())

    def _apply_ticket_symbol(self) -> None:
        code = self.ticket_code.text().strip().upper()
        if code in self.stocks:
            self._set_active_symbol(code)
        else:
            self.symbol_input.setText(code)
            self._search_or_add_symbol()

    def _set_active_symbol(self, code: str) -> None:
        if code not in self.stocks:
            return
        self.active_code = code
        stock = self.stocks[code]
        self.ticket_code.setText(code)
        self.ticket_name.setText(stock.name)
        self.price_spin.setValue(stock.price)
        self._refresh_quote_panel()
        self._refresh_order_book()
        self._refresh_chart()

    def _reset_ticket(self) -> None:
        stock = self.stocks[self.active_code]
        self.ticket_code.setText(stock.code)
        self.ticket_name.setText(stock.name)
        self.side_combo.setCurrentIndex(0)
        self.qty_spin.setValue(10)
        self.price_spin.setValue(stock.price)
        self.order_type.setCurrentIndex(0)

    def _tick_market(self) -> None:
        self.clock_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if not self.live_updates:
            return
        for stock in self.stocks.values():
            unit = self._price_unit(stock.price)
            delta = random.choice([-3, -2, -1, 0, 1, 2, 3]) * unit
            stock.price = max(unit, stock.price + delta)
            stock.high_price = max(stock.high_price, stock.price)
            stock.low_price = min(stock.low_price, stock.price)
            stock.volume += random.randint(500, 8000)
            stock.history.append(stock.price)
            if len(stock.history) > 80:
                stock.history.pop(0)
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._refresh_market_strip()
        self._refresh_watchlist()
        self._refresh_quote_panel()
        self._refresh_order_book()
        self._refresh_chart()
        self._refresh_portfolio()
        self._refresh_account_summary()

    def _refresh_market_strip(self) -> None:
        kospi = 2750 + sum(s.change_rate for s in self.stocks.values()) / max(len(self.stocks), 1)
        kosdaq = 870 + random.uniform(-2.5, 2.5)
        self.market_strip.setText(
            f"KOSPI {kospi:,.2f}   KOSDAQ {kosdaq:,.2f}   "
            f"USD/KRW 1,365.20   계좌 {self.account_no}   모드 {self.env_combo.currentText()}"
        )

    def _refresh_watchlist(self) -> None:
        self.watch_table.setRowCount(len(self.stocks))
        for row, stock in enumerate(self.stocks.values()):
            values = [
                stock.code,
                stock.name,
                f"{stock.price:,}",
                f"{stock.change:+,}",
                f"{stock.change_rate:+.2f}%",
                f"{stock.volume:,}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                if col in (3, 4):
                    self._color_item_by_number(item, stock.change)
                self.watch_table.setItem(row, col, item)
            if stock.code == self.active_code:
                self.watch_table.selectRow(row)

    def _refresh_quote_panel(self) -> None:
        stock = self.stocks[self.active_code]
        self.quote_name.setText(f"{stock.name} ({stock.code})")
        self.quote_price.setText(f"{stock.price:,}")
        self.quote_change.setText(f"대비 {stock.change:+,} / {stock.change_rate:+.2f}%")
        self.quote_change.setStyleSheet(
            f"color:{HtsColors.BUY if stock.change >= 0 else HtsColors.SELL};"
        )
        self.quote_ohlv.setText(
            f"시 {stock.open_price:,}  고 {stock.high_price:,}  저 {stock.low_price:,}  거래량 {stock.volume:,}"
        )
        self.ticket_name.setText(stock.name)
        if self.ticket_code.text().strip().upper() == stock.code:
            self.price_spin.setValue(stock.price)
        self.detail_labels["시가"].setText(f"{stock.open_price:,}")
        self.detail_labels["고가"].setText(f"{stock.high_price:,}")
        self.detail_labels["저가"].setText(f"{stock.low_price:,}")
        self.detail_labels["전일종가"].setText(f"{stock.previous_close:,}")
        self.detail_labels["거래량"].setText(f"{stock.volume:,}")
        self.detail_labels["주문가능"].setText(f"{self.cash:,} 원")

    def _refresh_order_book(self) -> None:
        stock = self.stocks[self.active_code]
        unit = self._price_unit(stock.price)
        mid = 9
        for row in range(20):
            level = mid - row
            price = stock.price + level * unit
            ask_qty = random.randint(50, 3000) if row <= mid else ""
            bid_qty = random.randint(50, 3000) if row >= mid else ""

            sell_btn = QPushButton("매도")
            sell_btn.setStyleSheet(f"background:{HtsColors.SELL};")
            sell_btn.clicked.connect(lambda _, p=price: self._order_from_book("매도", p))
            buy_btn = QPushButton("매수")
            buy_btn.setStyleSheet(f"background:{HtsColors.BUY};")
            buy_btn.clicked.connect(lambda _, p=price: self._order_from_book("매수", p))

            self.order_book_table.setCellWidget(row, 0, sell_btn)
            self._set_table_text(self.order_book_table, row, 1, f"{ask_qty:,}" if ask_qty else "")
            price_item = self._table_item(f"{price:,}")
            if row < mid:
                price_item.setForeground(QColor(HtsColors.BUY))
            elif row > mid:
                price_item.setForeground(QColor(HtsColors.SELL))
            self.order_book_table.setItem(row, 2, price_item)
            self._set_table_text(self.order_book_table, row, 3, f"{bid_qty:,}" if bid_qty else "")
            self.order_book_table.setCellWidget(row, 4, buy_btn)

    def _refresh_chart(self) -> None:
        stock = self.stocks[self.active_code]
        history = stock.history[-30:]
        self.chart_table.setRowCount(len(history))
        for row, price in enumerate(history):
            self._set_table_text(self.chart_table, row, 0, str(row + 1))
            self._set_table_text(self.chart_table, row, 1, f"{price:,}")

    def _refresh_portfolio(self) -> None:
        self.portfolio_table.setRowCount(len(self.positions))
        for row, (code, pos) in enumerate(self.positions.items()):
            stock = self.stocks.get(code)
            current = stock.price if stock else int(pos["avg"])
            qty = int(pos["qty"])
            avg = int(pos["avg"])
            value = qty * current
            pnl = (current - avg) * qty
            values = [str(pos["name"]), f"{qty:,}", f"{avg:,}", f"{current:,}", f"{value:,}", f"{pnl:+,}"]
            for col, value_text in enumerate(values):
                item = self._table_item(value_text)
                if col == 5:
                    self._color_item_by_number(item, pnl)
                self.portfolio_table.setItem(row, col, item)

    def _refresh_account_summary(self) -> None:
        stock_value = 0
        pnl = 0
        for code, pos in self.positions.items():
            stock = self.stocks.get(code)
            current = stock.price if stock else int(pos["avg"])
            qty = int(pos["qty"])
            avg = int(pos["avg"])
            stock_value += current * qty
            pnl += (current - avg) * qty
        total = self.cash + stock_value
        self.cash_label.setText(f"{self.cash:,} 원")
        self.account_summary.setText(
            f"예수금 {self.cash:,} 원\n평가금액 {stock_value:,} 원\n총자산 {total:,} 원\n손익 {pnl:+,} 원"
        )

    def _order_from_book(self, side: str, price: int) -> None:
        self.side_combo.setCurrentText(side)
        self.price_spin.setValue(price)
        self._submit_ticket(side)

    def _submit_ticket(self, side: Optional[str] = None) -> None:
        code = self.ticket_code.text().strip().upper()
        if code not in self.stocks:
            QMessageBox.warning(self, "주문 오류", "등록되지 않은 종목코드입니다.")
            return
        side = side or self.side_combo.currentText()
        qty = self.qty_spin.value()
        price = int(self.price_spin.value())
        stock = self.stocks[code]
        amount = qty * price
        order_type = self.order_type.currentText()

        msg = f"{stock.name}({code}) {side} {qty:,}주 / {price:,}원 / {order_type}"
        if QMessageBox.question(self, "주문 확인", msg) != QMessageBox.Yes:
            return

        if side == "매수" and amount > self.cash:
            QMessageBox.warning(self, "주문 거부", "예수금이 부족합니다.")
            self.log("주문거부", f"{msg} - 예수금 부족")
            return

        status = "데모접수" if self.env_combo.currentText() == "demo" else "전송대기"
        order = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "no": f"A{self.order_seq:06d}",
            "code": code,
            "side": side,
            "qty": f"{qty}",
            "price": f"{price}",
            "status": status,
            "env": self.env_combo.currentText(),
        }
        self.order_seq += 1
        self.orders.insert(0, order)
        self._apply_demo_fill(code, side, qty, price)
        self._refresh_orders_table()
        self._refresh_portfolio()
        self._refresh_account_summary()
        self.log("주문", f"{order['no']} {msg} - {status}")

    def _apply_demo_fill(self, code: str, side: str, qty: int, price: int) -> None:
        stock = self.stocks[code]
        if side == "매수":
            self.cash -= qty * price
            pos = self.positions.setdefault(code, {"name": stock.name, "qty": 0, "avg": price})
            old_qty = int(pos["qty"])
            old_avg = int(pos["avg"])
            new_qty = old_qty + qty
            pos["avg"] = int(((old_qty * old_avg) + (qty * price)) / max(new_qty, 1))
            pos["qty"] = new_qty
        else:
            pos = self.positions.get(code)
            if not pos:
                return
            sell_qty = min(qty, int(pos["qty"]))
            self.cash += sell_qty * price
            pos["qty"] = int(pos["qty"]) - sell_qty
            if int(pos["qty"]) <= 0:
                self.positions.pop(code, None)

    def _refresh_orders_table(self) -> None:
        self.orders_table.setRowCount(len(self.orders))
        for row, order in enumerate(self.orders):
            values = [
                order["time"],
                order["no"],
                order["code"],
                order["side"],
                order["qty"],
                f"{int(order['price']):,}",
                order["status"],
                order["env"],
            ]
            for col, value in enumerate(values):
                item = self._table_item(value)
                if col == 3:
                    item.setForeground(QColor(HtsColors.BUY if value == "매수" else HtsColors.SELL))
                self.orders_table.setItem(row, col, item)

    def log(self, category: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] [{category}] {message}")
        self.log_box.ensureCursorVisible()
        self.statusBar().showMessage(message, 3000)

    def _set_table_text(self, table: QTableWidget, row: int, col: int, text: str) -> None:
        table.setItem(row, col, self._table_item(text))

    def _table_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _color_item_by_number(self, item: QTableWidgetItem, value: int | float) -> None:
        if value > 0:
            item.setForeground(QColor(HtsColors.BUY))
        elif value < 0:
            item.setForeground(QColor(HtsColors.SELL))
        else:
            item.setForeground(QColor(HtsColors.MUTED))

    def _price_unit(self, price: int) -> int:
        if price < 1000:
            return 1
        if price < 5000:
            return 5
        if price < 10000:
            return 10
        if price < 50000:
            return 50
        if price < 100000:
            return 100
        if price < 500000:
            return 500
        return 1000


def main() -> None:
    app = QApplication(sys.argv)
    window = AutoStockHts()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
