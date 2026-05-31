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

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
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
        self.book_order_qty: Dict[str, Dict[str, Dict[int, int]]] = {}
        self.order_book_prices: Dict[int, int] = {}
        self.order_book_anchor_prices: Dict[str, int] = {}
        self.order_book_slider_values: Dict[str, int] = {}
        self.order_book_rows = 40
        self.order_cancel_drag = None
        self.skip_next_order_book_click = False
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
            "122630": ("KODEX레버리지", 346000),
            "252670": ("KODEX200선물인버스2X", 894000),
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
                font-size: 8pt;
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
                font-size: 8pt;
                font-weight: 600;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background: #0f172a;
                color: {HtsColors.TEXT};
                border: 1px solid {HtsColors.GRID};
                border-radius: 4px;
                padding: 4px;
                font-size: 8pt;
            }}
            QPushButton {{
                background: #334155;
                color: #ffffff;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 8pt;
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
                font-size: 8pt;
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
        root_layout.setSpacing(6)

        self.market_strip = QLabel()
        self.market_strip.setFrameShape(QFrame.StyledPanel)
        self.market_strip.setStyleSheet(
            "background:#0f172a; border:1px solid #374151; padding:6px;"
        )
        root_layout.addWidget(self.market_strip)

        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(self._build_order_book_tab(), "호가/주문")
        self.main_tabs.addTab(self._build_account_panel(), "계좌/잔고")
        self.main_tabs.addTab(self._build_watchlist_tab(), "관심종목")
        self.main_tabs.addTab(self._build_news_tab(), "뉴스/알림")
        self.main_tabs.addTab(self._build_log_tab(), "로그창")
        self.main_tabs.addTab(self._build_orders_tab(), "주문/체결")
        root_layout.addWidget(self.main_tabs, 1)

        self.setCentralWidget(root)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        title = QLabel("  AutoStock HTS  ")
        title.setFont(QFont("Malgun Gothic", 8, QFont.Bold))
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

    def _compact_light_table_style(self) -> str:
        return """
            QTableWidget {
                background: #f8fafc;
                color: #111827;
                gridline-color: #cbd5e1;
                selection-background-color: #334155;
                selection-color: #ffffff;
                border: 1px solid #94a3b8;
                font-size: 8pt;
            }
            QTableWidget::item {
                padding: 0px 2px;
                font-size: 8pt;
            }
            QHeaderView::section {
                background: #e5e7eb;
                color: #111827;
                border: 1px solid #cbd5e1;
                padding: 1px 2px;
                font-size: 8pt;
                font-weight: 400;
            }
            """

    def _build_order_book_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        book_columns = [56, 74, 66, 58, 74, 56]
        book_width = sum(book_columns) + 2

        order_top = QWidget()
        order_top.setFixedWidth(book_width)
        order_top_layout = QHBoxLayout(order_top)
        order_top_layout.setContentsMargins(0, 0, 0, 0)
        order_top_layout.setSpacing(2)

        self.order_account_combo = QComboBox()
        self.order_account_combo.addItem(self.account_no)
        self.order_account_combo.setFixedSize(82, 22)
        self.order_password_input = QLineEdit()
        self.order_password_input.setEchoMode(QLineEdit.Password)
        self.order_password_input.setPlaceholderText("계좌비밀번호")
        self.order_password_input.setFixedSize(88, 22)
        self.order_symbol_combo = QComboBox()
        self.order_symbol_combo.setEditable(True)
        self.order_symbol_combo.setFixedSize(84, 22)
        for code, stock in self.stocks.items():
            self.order_symbol_combo.addItem(code, stock.name)
        self.order_symbol_combo.setCurrentText(self.active_code)
        self.order_symbol_name = QLabel()
        self.order_symbol_name.setFrameShape(QFrame.StyledPanel)
        self.order_symbol_name.setFixedSize(124, 22)
        self.order_symbol_name.setAlignment(Qt.AlignCenter)
        self.order_symbol_name.setStyleSheet(
            "background:#f8fafc; color:#111827; padding:2px; font-size:8pt;"
        )

        order_top_layout.addWidget(self.order_account_combo)
        order_top_layout.addWidget(self.order_password_input)
        order_top_layout.addWidget(self.order_symbol_combo)
        order_top_layout.addWidget(self.order_symbol_name)
        layout.addWidget(order_top, 0, Qt.AlignLeft)

        self.order_holdings_table = QTableWidget(4, 4)
        self.order_holdings_table.setHorizontalHeaderLabels(["종목명", "보유량", "현재가", "평가금액"])
        self.order_holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.order_holdings_table.verticalHeader().setVisible(False)
        self.order_holdings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.order_holdings_table.verticalHeader().setMinimumSectionSize(16)
        self.order_holdings_table.verticalHeader().setDefaultSectionSize(16)
        self.order_holdings_table.horizontalHeader().setFixedHeight(18)
        self.order_holdings_table.setFixedHeight(84)
        self.order_holdings_table.setFixedWidth(book_width)
        self.order_holdings_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.order_holdings_table.setFont(QFont("Malgun Gothic", 8))
        self.order_holdings_table.horizontalHeader().setFont(QFont("Malgun Gothic", 8))
        self.order_holdings_table.setStyleSheet(self._compact_light_table_style())
        for col, width in enumerate([110, 64, 86, 124]):
            self.order_holdings_table.setColumnWidth(col, width)
        layout.addWidget(self.order_holdings_table, 0, Qt.AlignLeft)

        book_layout = QHBoxLayout()
        book_layout.setContentsMargins(0, 0, 0, 0)
        book_layout.setSpacing(2)

        self.order_book_table = QTableWidget(self.order_book_rows, 6)
        self.order_book_table.setHorizontalHeaderLabels(
            ["KRX매도", "잔량", "호가", "등락율", "잔량", "KRX매수"]
        )
        self.order_book_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.order_book_table.verticalHeader().setVisible(False)
        self.order_book_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.order_book_table.verticalHeader().setMinimumSectionSize(16)
        self.order_book_table.verticalHeader().setDefaultSectionSize(16)
        self.order_book_table.horizontalHeader().setFixedHeight(18)
        self.order_book_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.order_book_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.order_book_table.setFixedHeight(660)
        self.order_book_table.setFont(QFont("Malgun Gothic", 8))
        self.order_book_table.horizontalHeader().setFont(QFont("Malgun Gothic", 8))
        self.order_book_table.setStyleSheet(self._compact_light_table_style())
        for col, width in enumerate(book_columns):
            self.order_book_table.setColumnWidth(col, width)
        self.order_book_table.setFixedWidth(book_width)
        self.order_book_table.viewport().installEventFilter(self)
        book_layout.addWidget(self.order_book_table, 0, Qt.AlignLeft | Qt.AlignTop)

        self.order_book_slider = QSlider(Qt.Vertical)
        self.order_book_slider.setRange(-200, 200)
        self.order_book_slider.setValue(0)
        self.order_book_slider.setSingleStep(1)
        self.order_book_slider.setPageStep(5)
        self.order_book_slider.setToolTip("호가 가격대를 수동으로 이동")
        book_layout.addWidget(self.order_book_slider, 0, Qt.AlignLeft | Qt.AlignTop)
        book_layout.addStretch(1)

        layout.addLayout(book_layout, 1)
        return widget

    def _build_watchlist_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.watch_table = QTableWidget(0, 6)
        self.watch_table.setHorizontalHeaderLabels(["코드", "종목명", "현재가", "대비", "등락률", "거래량"])
        self.watch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.watch_table.verticalHeader().setVisible(False)
        self.watch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.watch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.watch_table)
        return widget

    def _build_news_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.news_box = QTextEdit()
        self.news_box.setReadOnly(True)
        self.news_box.setText(
            "09:00 장 시작\n09:05 삼성전자 외국인 순매수 유입\n"
            "09:12 반도체 업종 강세\n09:30 데모 모드: 주문은 실제 전송되지 않음"
        )
        layout.addWidget(self.news_box)
        return widget

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)
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

    def _build_account_panel(self) -> QGroupBox:
        group = QGroupBox("계좌/잔고")
        layout = QVBoxLayout(group)

        self.account_summary = QLabel()
        self.account_summary.setStyleSheet("font-size:8pt; font-weight:400;")
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
        self.watch_table.itemSelectionChanged.connect(self._select_watch_symbol)
        self.order_book_table.cellClicked.connect(self._handle_order_book_click)
        self.order_book_slider.valueChanged.connect(self._handle_order_book_slider)
        self.order_symbol_combo.activated.connect(lambda _: self._apply_order_symbol())
        if self.order_symbol_combo.lineEdit() is not None:
            self.order_symbol_combo.lineEdit().returnPressed.connect(self._apply_order_symbol)

    def _start_updates(self) -> None:
        self.live_updates = True
        self.statusBar().showMessage("실시간 업데이트 ON", 3000)
        self.log("시스템", "실시간 업데이트 ON")

    def _stop_updates(self) -> None:
        self.live_updates = False
        self.statusBar().showMessage("실시간 업데이트 OFF", 3000)
        self.log("시스템", "실시간 업데이트 OFF")

    def _search_or_add_symbol(self) -> None:
        code = self.order_symbol_combo.currentText().strip().upper()
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
            self._sync_order_symbol_options()
        self._set_active_symbol(code)
        self._refresh_all()

    def _select_watch_symbol(self) -> None:
        row = self.watch_table.currentRow()
        if row < 0:
            return
        item = self.watch_table.item(row, 0)
        if item:
            self._set_active_symbol(item.text())

    def eventFilter(self, watched, event) -> bool:
        if (
            hasattr(self, "order_book_table")
            and watched is self.order_book_table.viewport()
        ):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.order_cancel_drag = self._order_cancel_drag_candidate(event.pos())
            elif event.type() == QEvent.MouseMove and self.order_cancel_drag:
                if event.buttons() & Qt.LeftButton and not self.order_cancel_drag["rect"].contains(event.pos()):
                    drag = self.order_cancel_drag
                    self.order_cancel_drag = None
                    self.skip_next_order_book_click = True
                    self._request_book_order_cancel(
                        str(drag["code"]),
                        str(drag["side"]),
                        int(drag["price"]),
                        int(drag["qty"]),
                    )
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                self.order_cancel_drag = None
            elif event.type() == QEvent.Wheel:
                delta = event.angleDelta().y()
                if delta:
                    steps = max(1, abs(delta) // 120)
                    direction = 1 if delta > 0 else -1
                    self.order_book_slider.setValue(self.order_book_slider.value() + direction * steps)
                return True
        return super().eventFilter(watched, event)

    def _apply_ticket_symbol(self) -> None:
        code = self.order_symbol_combo.currentText().strip().upper()
        if code in self.stocks:
            self._set_active_symbol(code)
        else:
            self._search_or_add_symbol()

    def _apply_order_symbol(self) -> None:
        code = self.order_symbol_combo.currentText().strip().upper()
        if not code:
            return
        if code in self.stocks:
            self._set_active_symbol(code)
            self._refresh_all()
        else:
            self._search_or_add_symbol()

    def _set_active_symbol(self, code: str) -> None:
        if code not in self.stocks:
            return
        self.active_code = code
        stock = self.stocks[code]
        self.order_book_anchor_prices.setdefault(code, stock.price)
        self.order_book_slider_values.setdefault(code, 0)
        self._sync_order_symbol_options()
        self.order_symbol_combo.blockSignals(True)
        self.order_symbol_combo.setCurrentText(code)
        self.order_symbol_combo.blockSignals(False)
        self.order_symbol_name.setText(stock.name)
        self._refresh_quote_panel()
        self._refresh_order_book()

    def _sync_order_symbol_options(self) -> None:
        if not hasattr(self, "order_symbol_combo"):
            return
        existing = {
            self.order_symbol_combo.itemText(index)
            for index in range(self.order_symbol_combo.count())
        }
        for code, stock in self.stocks.items():
            if code not in existing:
                self.order_symbol_combo.addItem(code, stock.name)

    def _reset_ticket(self) -> None:
        stock = self.stocks[self.active_code]
        self.order_symbol_combo.setCurrentText(stock.code)
        self.order_symbol_name.setText(stock.name)

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
        self._refresh_portfolio()
        self._refresh_order_holdings()
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
        self.order_symbol_name.setText(stock.name)

    def _refresh_order_book(self) -> None:
        stock = self.stocks[self.active_code]
        unit = self._price_unit(stock.price)
        if self.order_book_table.rowCount() != self.order_book_rows:
            self.order_book_table.setRowCount(self.order_book_rows)
        rows = self.order_book_table.rowCount()
        mid = rows // 2 - 1
        order_qty = self.book_order_qty.get(stock.code, {})
        slider_value = self.order_book_slider_values.get(stock.code, 0)
        self.order_book_slider.blockSignals(True)
        self.order_book_slider.setValue(slider_value)
        self.order_book_slider.blockSignals(False)
        center_price = self._order_book_center_price(stock.code, stock.price, unit)
        previous_close_price = max(unit, round(stock.previous_close / unit) * unit)
        current_price_level = max(unit, round(stock.price / unit) * unit)
        self.order_book_prices = {}
        for row in range(rows):
            level = mid - row
            price = max(unit, center_price + level * unit)
            self.order_book_prices[row] = price
            show_ask_qty = current_price_level < price <= current_price_level + unit * 10
            show_bid_qty = current_price_level - unit * 9 <= price <= current_price_level
            ask_qty = random.randint(50, 3000) if show_ask_qty else ""
            bid_qty = random.randint(50, 3000) if show_bid_qty else ""
            sell_order_qty = order_qty.get("매도", {}).get(price, 0)
            buy_order_qty = order_qty.get("매수", {}).get(price, 0)
            change = price - stock.previous_close
            change_rate = change / stock.previous_close * 100 if stock.previous_close else 0.0
            is_previous_close = price == previous_close_price

            self.order_book_table.setRowHeight(row, 16)
            self._set_order_book_item(row, 0, f"{sell_order_qty:,}" if sell_order_qty else "", "#dbeafe")
            self._set_order_book_item(row, 1, f"{ask_qty:,}" if ask_qty else "", "#eff6ff")
            price_item = self._table_item(f"{price:,}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_item.setBackground(QColor("#fff7ed" if row == mid else "#ffffff"))
            price_item.setFont(QFont("Consolas", 8, QFont.Bold))
            if is_previous_close:
                price_item.setForeground(QColor("#111827"))
            elif price > stock.previous_close:
                price_item.setForeground(QColor(HtsColors.BUY))
            else:
                price_item.setForeground(QColor(HtsColors.SELL))
            self.order_book_table.setItem(row, 2, price_item)
            self._set_order_book_item(row, 3, f"{change_rate:+.2f}", "#ffffff", change, is_previous_close)
            self._set_order_book_item(row, 4, f"{bid_qty:,}" if bid_qty else "", "#fef2f2")
            self._set_order_book_item(row, 5, f"{buy_order_qty:,}" if buy_order_qty else "", "#fee2e2")

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

    def _refresh_order_holdings(self) -> None:
        self.order_holdings_table.setRowCount(4)
        holdings = list(self.positions.items())[:4]
        for row in range(4):
            self.order_holdings_table.setRowHeight(row, 16)
            if row >= len(holdings):
                for col in range(4):
                    self._set_table_text(self.order_holdings_table, row, col, "")
                continue
            code, pos = holdings[row]
            stock = self.stocks.get(code)
            current = stock.price if stock else int(pos["avg"])
            qty = int(pos["qty"])
            values = [
                str(pos["name"]),
                f"{qty:,}",
                f"{current:,}",
                f"{qty * current:,}",
            ]
            for col, value in enumerate(values):
                item = self._table_item(value)
                item.setFont(QFont("Malgun Gothic", 8))
                if col:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.order_holdings_table.setItem(row, col, item)

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
        self._submit_ticket(side, price)

    def _handle_order_book_click(self, row: int, col: int) -> None:
        if self.skip_next_order_book_click:
            self.skip_next_order_book_click = False
            return
        if col not in (0, 5):
            return
        price = self.order_book_prices.get(row)
        if price is None:
            return
        self._order_from_book("매도" if col == 0 else "매수", price)

    def _order_cancel_drag_candidate(self, pos):
        row = self.order_book_table.rowAt(pos.y())
        col = self.order_book_table.columnAt(pos.x())
        if row < 0 or col not in (0, 5):
            return None
        price = self.order_book_prices.get(row)
        if price is None:
            return None
        side = "매도" if col == 0 else "매수"
        qty = self.book_order_qty.get(self.active_code, {}).get(side, {}).get(price, 0)
        if qty <= 0:
            return None
        index = self.order_book_table.model().index(row, col)
        return {
            "code": self.active_code,
            "side": side,
            "price": price,
            "qty": qty,
            "rect": self.order_book_table.visualRect(index),
        }

    def _request_book_order_cancel(self, code: str, side: str, price: int, qty: int) -> None:
        stock = self.stocks.get(code)
        name = stock.name if stock else code
        msg = f"{name}({code}) {side} {qty:,}주 / {price:,}원 주문을 취소 요청하시겠습니까?"
        if QMessageBox.question(self, "주문 취소 확인", msg) != QMessageBox.Yes:
            return

        by_side = self.book_order_qty.get(code, {}).get(side, {})
        by_side.pop(price, None)
        cancel_order = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "no": f"C{self.order_seq:06d}",
            "code": code,
            "side": side,
            "qty": f"{qty}",
            "price": f"{price}",
            "status": "취소요청",
            "env": self.env_combo.currentText(),
        }
        self.order_seq += 1
        self.orders.insert(0, cancel_order)
        self._refresh_order_book()
        self._refresh_orders_table()
        self.log("주문취소", f"{cancel_order['no']} {msg}")

    def _handle_order_book_slider(self, value: int) -> None:
        self.order_book_slider_values[self.active_code] = value
        self._refresh_order_book()

    def _order_book_center_price(self, code: str, current_price: int, unit: int) -> int:
        anchor = self.order_book_anchor_prices.setdefault(code, current_price)
        slider_value = self.order_book_slider_values.setdefault(code, 0)
        return max(unit, anchor + slider_value * unit)

    def _submit_ticket(self, side: Optional[str] = None, price: Optional[int] = None) -> None:
        code = self.order_symbol_combo.currentText().strip().upper()
        if code not in self.stocks:
            QMessageBox.warning(self, "주문 오류", "등록되지 않은 종목코드입니다.")
            return
        side = side or "매수"
        qty = 10
        price = int(price or self.stocks[code].price)
        stock = self.stocks[code]
        amount = qty * price
        order_type = "지정가"

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
        self._record_book_order(code, side, qty, price)
        self._apply_demo_fill(code, side, qty, price)
        self._refresh_order_book()
        self._refresh_orders_table()
        self._refresh_portfolio()
        self._refresh_order_holdings()
        self._refresh_account_summary()
        self.log("주문", f"{order['no']} {msg} - {status}")

    def _record_book_order(self, code: str, side: str, qty: int, price: int) -> None:
        by_side = self.book_order_qty.setdefault(code, {}).setdefault(side, {})
        by_side[price] = by_side.get(price, 0) + qty

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

    def _set_order_book_item(
        self,
        row: int,
        col: int,
        text: str,
        background: str,
        value: Optional[float] = None,
        use_black: bool = False,
    ) -> None:
        item = self._table_item(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setFont(QFont("Malgun Gothic", 8))
        item.setBackground(QColor(background))
        if col in (1, 3, 4):
            item.setFont(QFont("Consolas", 8))
        if use_black:
            item.setForeground(QColor("#111827"))
        elif value is not None:
            self._color_item_by_number(item, value)
        elif col == 0 and text:
            item.setForeground(QColor(HtsColors.SELL))
            item.setFont(QFont("Malgun Gothic", 8))
        elif col == 5 and text:
            item.setForeground(QColor(HtsColors.BUY))
            item.setFont(QFont("Malgun Gothic", 8))
        self.order_book_table.setItem(row, col, item)

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
    app.setFont(QFont("Malgun Gothic", 8))
    window = AutoStockHts()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
