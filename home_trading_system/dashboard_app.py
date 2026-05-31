#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AutoStock 대시보드 - PyQt5 기반 데스크톱 애플리케이션
"""

import sys
import threading
import time
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QTabWidget, QGroupBox, QGridLayout, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

# 프로젝트 루트 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "examples_user"))

try:
    import kis_auth as ka
except ImportError:
    # 절대 경로 시도
    sys.path.insert(0, str(project_root / "examples_user"))
    import kis_auth as ka

from examples_user.domestic_stock import domestic_stock_functions as dsf
from examples_user.domestic_stock.domestic_stock_functions_ws import asking_price_krx
import pandas as pd

# kis_auth 설정
_cfg = ka.getEnv()


class SignalEmitter(QObject):
    """스레드에서 신호를 보내기 위한 헬퍼"""
    update_signal = pyqtSignal(str, str)  # (key, value)
    error_signal = pyqtSignal(str)


class ClickableLineEdit(QLineEdit):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AutoStockDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signal_emitter = SignalEmitter()
        self.signal_emitter.update_signal.connect(self.update_dashboard)
        self.signal_emitter.error_signal.connect(self.show_error)
        
        self.setWindowTitle("AutoStock 대시보드")
        self.setGeometry(100, 100, 1200, 800)
        
        # 인증 처리
        self.init_auth()
        self.ws_thread = None
        self.kws = None
        self.order_panels = {}
        self.order_symbols = {1: None, 2: None}
        self.panel_by_symbol = {}
        self.order_book_active = False
        self.order_env = "demo"
        self.default_order_qty = "10"
        self.current_price_values = {1: None, 2: None}
        self.active_orders = {1: set(), 2: set()}
        
        # UI 초기화
        self.init_ui()
        
        # 타이머 설정 (주기적 업데이트)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.periodic_update)
        self.update_timer.start(5000)  # 5초마다 업데이트
        
        # 초기 데이터 로드
        self.load_initial_data()
    
    def init_auth(self):
        """KIS 인증 처리"""
        try:
            ka.auth(svr="vps", product="01")
            self.cano = str(_cfg["my_paper_stock"])[:8]
            self.acnt_prdt_cd = "01"
        except Exception as e:
            print(f"인증 오류: {e}")
            self.cano = "50187261"
            self.acnt_prdt_cd = "01"
    
    def init_ui(self):
        """UI 초기화"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        
        # 탭 생성
        self.tabs = QTabWidget()
        self.account_tab = self.create_account_tab()
        self.order_tab = self.create_order_tab()
        self.tabs.addTab(self.order_tab, "호가주문")
        self.tabs.addTab(self.account_tab, "계좌 정보")
        self.is_account_first = False
        self.tabs.setCurrentIndex(0)

        main_layout.addWidget(self.tabs)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(160)
        self.log_box.setStyleSheet("background:#ffffff; color:#000000; border:1px solid #cccccc;")
        main_layout.addWidget(self.log_box)

        central_widget.setLayout(main_layout)
    
    def create_account_tab(self):
        """계좌 정보 탭"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 계좌 정보 그룹
        account_group = QGroupBox("계좌 정보")
        account_layout = QGridLayout()
        
        # 계좌번호
        account_layout.addWidget(QLabel("계좌번호:"), 0, 0)
        self.account_label = QLabel(self.cano)
        self.account_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        account_layout.addWidget(self.account_label, 0, 1)
        
        # 총 자산
        account_layout.addWidget(QLabel("총 자산:"), 1, 0)
        self.total_asset_label = QLabel("로딩 중...")
        self.total_asset_label.setStyleSheet("font-weight: bold; color: blue; font-size: 14px;")
        account_layout.addWidget(self.total_asset_label, 1, 1)
        
        # 미체결 금액
        account_layout.addWidget(QLabel("미체결 금액:"), 2, 0)
        self.pending_label = QLabel("로딩 중...")
        account_layout.addWidget(self.pending_label, 2, 1)
        
        # 평가 자산
        account_layout.addWidget(QLabel("평가 자산:"), 3, 0)
        self.eval_asset_label = QLabel("로딩 중...")
        account_layout.addWidget(self.eval_asset_label, 3, 1)
        
        # 손익/손익율
        account_layout.addWidget(QLabel("손익 / 손익율:"), 4, 0)
        self.pnl_label = QLabel("로딩 중...")
        self.pnl_label.setStyleSheet("font-weight: bold; color: green; font-size: 12px;")
        account_layout.addWidget(self.pnl_label, 4, 1)
        
        # 마지막 업데이트 시간
        account_layout.addWidget(QLabel("마지막 업데이트:"), 5, 0)
        self.update_time_label = QLabel("")
        account_layout.addWidget(self.update_time_label, 5, 1)
        
        account_group.setLayout(account_layout)
        layout.addWidget(account_group)
        
        # 잔고 테이블
        balance_group = QGroupBox("보유 종목")
        balance_layout = QVBoxLayout()
        
        self.balance_table = QTableWidget()
        self.balance_table.setColumnCount(6)
        self.balance_table.setHorizontalHeaderLabels([
            "종목코드", "종목명", "수량", "평균가", "평가가", "손익"
        ])
        self.balance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        balance_layout.addWidget(self.balance_table)
        
        balance_group.setLayout(balance_layout)
        layout.addWidget(balance_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_order_tab(self):
        """호가주문 탭"""
        widget = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)

        left_panel = self.create_order_panel(1, "005930")
        right_panel = self.create_order_panel(2, "035420")

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 1)

        widget.setLayout(main_layout)
        return widget

    def create_order_panel(self, panel_id, default_symbol):
        panel = QWidget()
        panel_layout = QVBoxLayout()
        panel_layout.setSpacing(4)

        self.order_panels[panel_id] = {}

        search_group = QGroupBox(f"종목 검색 {panel_id}")
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("종목코드:"))

        symbol_input = QLineEdit()
        symbol_input.setPlaceholderText("예: 005930")
        symbol_input.setText(default_symbol)
        symbol_input.setFixedWidth(80)
        self.order_panels[panel_id]["symbol_input"] = symbol_input
        search_layout.addWidget(symbol_input)

        search_btn = QPushButton("조회")
        search_btn.clicked.connect(lambda _, pid=panel_id: self.search_symbol(pid))
        search_btn.setFixedWidth(44)
        search_layout.addWidget(search_btn)

        search_layout.addWidget(QLabel("종목명:"))
        self.order_panels[panel_id]["search_symbol_name_label"] = QLabel("-")
        self.order_panels[panel_id]["search_symbol_name_label"].setStyleSheet("font-weight: bold;")
        self.order_panels[panel_id]["search_symbol_name_label"].setMinimumWidth(120)
        search_layout.addWidget(self.order_panels[panel_id]["search_symbol_name_label"], 1)

        search_group.setLayout(search_layout)
        panel_layout.addWidget(search_group)

        info_group = QGroupBox("종목 정보")
        info_layout = QGridLayout()
        info_layout.setVerticalSpacing(4)
        info_layout.setHorizontalSpacing(16)

        info_layout.addWidget(QLabel("종목명:"), 0, 0)
        self.order_panels[panel_id]["symbol_name_label"] = QLabel("-")
        self.order_panels[panel_id]["symbol_name_label"].setStyleSheet("font-weight: bold; font-size: 12px;")
        info_layout.addWidget(self.order_panels[panel_id]["symbol_name_label"], 0, 1)

        info_layout.addWidget(QLabel("현재가:"), 0, 2)
        self.order_panels[panel_id]["current_price_label"] = QLabel("-")
        self.order_panels[panel_id]["current_price_label"].setStyleSheet("font-weight: bold; color: black; font-size: 12px;")
        info_layout.addWidget(self.order_panels[panel_id]["current_price_label"], 0, 3)

        info_layout.addWidget(QLabel("시가:"), 1, 0)
        self.order_panels[panel_id]["open_price_label"] = QLabel("-")
        info_layout.addWidget(self.order_panels[panel_id]["open_price_label"], 1, 1)

        info_layout.addWidget(QLabel("고가:"), 1, 2)
        self.order_panels[panel_id]["high_price_label"] = QLabel("-")
        info_layout.addWidget(self.order_panels[panel_id]["high_price_label"], 1, 3)

        info_layout.addWidget(QLabel("저가:"), 2, 0)
        self.order_panels[panel_id]["low_price_label"] = QLabel("-")
        info_layout.addWidget(self.order_panels[panel_id]["low_price_label"], 2, 1)

        info_layout.addWidget(QLabel("변동률:"), 2, 2)
        self.order_panels[panel_id]["change_rate_label"] = QLabel("-")
        self.order_panels[panel_id]["change_rate_label"].setStyleSheet("font-weight: bold; font-size: 12px;")
        info_layout.addWidget(self.order_panels[panel_id]["change_rate_label"], 2, 3)

        info_group.setLayout(info_layout)
        panel_layout.addWidget(info_group)

        order_book_group = QGroupBox("호가 창")
        order_book_layout = QGridLayout()
        order_book_layout.setVerticalSpacing(0)
        order_book_layout.setHorizontalSpacing(0)
        order_book_layout.setContentsMargins(0, 0, 0, 0)

        headers = ["매도주문", "매도잔량", "호가", "등락율", "매수잔량", "매수주문"]
        for col, label in enumerate(headers):
            hdr = QLabel(label)
            hdr.setStyleSheet("font-weight: bold; color: #000000; background:#e8e8e8; border:1px solid #cccccc; font-size:9px; padding:1px; margin:0px;")
            order_book_layout.addWidget(hdr, 0, col)

        self.order_book_depth = 40
        self.current_price_index = self.order_book_depth // 2 - 1
        self.order_panels[panel_id]["ask_order_inputs"] = []
        self.order_panels[panel_id]["ask_qty_labels"] = []
        self.order_panels[panel_id]["price_labels"] = []
        self.order_panels[panel_id]["change_rate_labels"] = []
        self.order_panels[panel_id]["bid_qty_labels"] = []
        self.order_panels[panel_id]["bid_order_inputs"] = []

        for idx in range(self.order_book_depth):
            ask_input = ClickableLineEdit()
            ask_input.setReadOnly(True)
            ask_input.setPlaceholderText(self.default_order_qty)
            ask_input.setText("")
            ask_input.setAlignment(Qt.AlignCenter)
            ask_input.clicked.connect(lambda _, pid=panel_id, row=idx: self.handle_click(pid, "SELL", row, "ask"))
            ask_input.setStyleSheet("background:#ffffff; color:#000000; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            ask_input.setFixedHeight(16)
            ask_input.setFixedWidth(40)
            self.order_panels[panel_id]["ask_order_inputs"].append(ask_input)
            order_book_layout.addWidget(ask_input, idx + 1, 0)

            ask_qty = QLabel("-")
            ask_qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ask_qty.setStyleSheet("color:#000000; background:#f0f0f0; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            self.order_panels[panel_id]["ask_qty_labels"].append(ask_qty)
            order_book_layout.addWidget(ask_qty, idx + 1, 1)

            price_label = QLabel("-")
            price_label.setAlignment(Qt.AlignCenter)
            price_label.setStyleSheet("color:#000000; background:#ffffff; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            self.order_panels[panel_id]["price_labels"].append(price_label)
            order_book_layout.addWidget(price_label, idx + 1, 2)

            change_rate = QLabel("-")
            change_rate.setAlignment(Qt.AlignCenter)
            change_rate.setStyleSheet("color:#000000; background:#f5f5f5; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            self.order_panels[panel_id]["change_rate_labels"].append(change_rate)
            order_book_layout.addWidget(change_rate, idx + 1, 3)

            bid_qty = QLabel("-")
            bid_qty.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            bid_qty.setStyleSheet("color:#000000; background:#f0f0f0; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            self.order_panels[panel_id]["bid_qty_labels"].append(bid_qty)
            order_book_layout.addWidget(bid_qty, idx + 1, 4)

            bid_input = ClickableLineEdit()
            bid_input.setReadOnly(True)
            bid_input.setPlaceholderText(self.default_order_qty)
            bid_input.setText("")
            bid_input.setAlignment(Qt.AlignCenter)
            bid_input.clicked.connect(lambda _, pid=panel_id, row=idx: self.handle_click(pid, "BUY", row, "bid"))
            bid_input.setStyleSheet("background:#ffffff; color:#000000; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
            bid_input.setFixedHeight(16)
            bid_input.setFixedWidth(40)
            self.order_panels[panel_id]["bid_order_inputs"].append(bid_input)
            order_book_layout.addWidget(bid_input, idx + 1, 5)

        order_book_group.setLayout(order_book_layout)
        panel_layout.addWidget(order_book_group)

        self.order_panels[panel_id]["order_status_label"] = QLabel("대기 중")
        self.order_panels[panel_id]["order_summary_label"] = QLabel("-")
        panel_layout.addWidget(QLabel("구독 상태:"))
        panel_layout.addWidget(self.order_panels[panel_id]["order_status_label"])
        panel_layout.addWidget(QLabel("요약:"))
        panel_layout.addWidget(self.order_panels[panel_id]["order_summary_label"])

        order_control_group = QGroupBox("주문 설정")
        order_control_layout = QVBoxLayout()
        qty_frame = QWidget()
        qty_layout = QHBoxLayout()
        qty_layout.addWidget(QLabel("기본 주문수량:"))
        qty_input = QLineEdit()
        qty_input.setText(self.default_order_qty)
        qty_input.setFixedHeight(24)
        self.order_panels[panel_id]["order_qty_input"] = qty_input
        qty_layout.addWidget(qty_input)
        qty_frame.setLayout(qty_layout)
        order_control_layout.addWidget(qty_frame)

        self.order_panels[panel_id]["order_message_label"] = QLabel("주문할 호가를 클릭하세요")
        order_control_layout.addWidget(self.order_panels[panel_id]["order_message_label"])
        order_control_group.setLayout(order_control_layout)
        panel_layout.addWidget(order_control_group)

        panel.setLayout(panel_layout)
        return panel

    def load_initial_data(self):
        """초기 데이터 로드"""
        # 백그라운드 스레드에서 계좌 정보 조회
        thread = threading.Thread(target=self.fetch_account_info)
        thread.daemon = True
        thread.start()
        
        # 종목 정보 조회 및 호가 구독 준비
        self.search_symbol(1)
        self.search_symbol(2)

    def swap_tabs(self):
        """계좌 정보 탭과 종목 조회 탭 순서를 교체합니다."""
        current_index = self.tabs.currentIndex()

        # 탭을 제거하되 위젯은 유지합니다.
        self.tabs.removeTab(1)
        self.tabs.removeTab(0)

        if self.is_account_first:
            self.tabs.addTab(self.symbol_tab, "종목 조회")
            self.tabs.addTab(self.account_tab, "계좌 정보")
            self.swap_tabs_btn.setText("기본 순서로")
        else:
            self.tabs.addTab(self.account_tab, "계좌 정보")
            self.tabs.addTab(self.symbol_tab, "종목 조회")
            self.swap_tabs_btn.setText("탭 순서 전환")

        self.is_account_first = not self.is_account_first
        if current_index >= self.tabs.count():
            current_index = self.tabs.count() - 1
        if current_index >= 0:
            self.tabs.setCurrentIndex(current_index)

    def fetch_account_info(self):
        """계좌 정보 조회"""
        try:
            api_url = "/uapi/domestic-stock/v1/trading/inquire-balance"
            tr_id = "VTTC8434R"
            
            params = {
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            
            res = ka._url_fetch(api_url, tr_id, "", params)
            
            if res.isOK():
                body = res.getBody()
                
                # 계좌 정보 (output2)
                if hasattr(body, 'output2') and body.output2:
                    info = body.output2[0]
                    
                    # 숫자 변환
                    def to_int(val):
                        try:
                            return int(val)
                        except:
                            return 0
                    
                    total_asset = to_int(info.get('dnca_tot_amt', 0))
                    eval_asset = to_int(info.get('tot_evlu_amt', 0))
                    pnl = to_int(info.get('asst_icdc_amt', 0))
                    pnl_rate = float(info.get('asst_icdc_erng_rt', 0))
                    pending = to_int(info.get('nxdy_excc_amt', 0))
                    
                    # 신호 발송
                    self.signal_emitter.update_signal.emit(
                        "total_asset",
                        f"{total_asset:,.0f} 원"
                    )
                    self.signal_emitter.update_signal.emit(
                        "eval_asset",
                        f"{eval_asset:,.0f} 원"
                    )
                    self.signal_emitter.update_signal.emit(
                        "pending",
                        f"{pending:,.0f} 원"
                    )
                    
                    pnl_text = f"{pnl:,.0f} 원 ({pnl_rate:.2f}%)"
                    color = "green" if pnl >= 0 else "red"
                    self.signal_emitter.update_signal.emit("pnl", pnl_text)
                
                # 보유 종목 (output1)
                if hasattr(body, 'output1') and body.output1:
                    self.update_balance_table(body.output1)
                
                self.signal_emitter.update_signal.emit(
                    "update_time",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
        
        except Exception as e:
            self.signal_emitter.error_signal.emit(f"계좌 조회 오류: {str(e)}")
    
    def update_balance_table(self, data):
        """보유 종목 테이블 업데이트"""
        try:
            self.balance_table.setRowCount(len(data))
            
            for row, item in enumerate(data):
                # 종목코드
                code = str(item.get('pdno', ''))
                self.balance_table.setItem(row, 0, QTableWidgetItem(code))
                
                # 종목명
                name = str(item.get('prdt_name', ''))
                self.balance_table.setItem(row, 1, QTableWidgetItem(name))
                
                # 수량
                qty = int(item.get('hldg_qty', 0))
                self.balance_table.setItem(row, 2, QTableWidgetItem(f"{qty:,.0f}"))
                
                # 평균가
                avg_price = int(item.get('pchs_avg_prc', 0))
                self.balance_table.setItem(row, 3, QTableWidgetItem(f"{avg_price:,.0f}"))
                
                # 평가가
                eval_price = int(item.get('prpr', 0))
                self.balance_table.setItem(row, 4, QTableWidgetItem(f"{eval_price:,.0f}"))
                
                # 손익
                pnl = int(item.get('evlu_pfls_amt', 0))
                pnl_item = QTableWidgetItem(f"{pnl:,.0f}")
                if pnl >= 0:
                    pnl_item.setForeground(QColor("green"))
                else:
                    pnl_item.setForeground(QColor("red"))
                self.balance_table.setItem(row, 5, pnl_item)
        
        except Exception as e:
            self.signal_emitter.error_signal.emit(f"테이블 업데이트 오류: {str(e)}")
    
    def search_symbol(self, panel_id):
        """종목 검색"""
        panel = self.order_panels.get(panel_id)
        if panel is None:
            return

        symbol = panel["symbol_input"].text().strip()
        if not symbol:
            return

        symbol = symbol.upper()
        self.order_symbols[panel_id] = symbol
        self.panel_by_symbol.setdefault(symbol, set()).add(panel_id)

        thread = threading.Thread(target=self.fetch_symbol_info, args=(panel_id, symbol))
        thread.daemon = True
        thread.start()

        self.start_order_book_subscription(panel_id, symbol)
    
    def fetch_symbol_info(self, panel_id, symbol):
        """종목 정보 조회"""
        try:
            df = dsf.inquire_price(
                env_dv="demo",
                fid_cond_mrkt_div_code="J",
                fid_input_iscd=symbol.upper()
            )
            
            if df is None or df.empty:
                self.signal_emitter.update_signal.emit(f"panel{panel_id}_order_book_status", f"종목 조회 결과 없음: {symbol}")
                return
            row = df.iloc[0]
            
            name = str(row.get('stck_kor_isnm') or row.get('hts_kor_isnm') or row.get('bstp_kor_isnm') or symbol)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_symbol_name", name)
            
            price = int(row.get('stck_prpr') or row.get('stck_sdpr') or 0)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_current_price", f"{price:,} 원")
            
            open_price = int(row.get('stck_oprc') or 0)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_open_price", f"{open_price:,} 원")
            
            high_price = int(row.get('stck_hgpr') or 0)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_high_price", f"{high_price:,} 원")
            
            low_price = int(row.get('stck_lwpr') or 0)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_low_price", f"{low_price:,} 원")
            
            volume = int(row.get('acml_vol') or row.get('vol') or 0)
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_volume", f"{volume:,}")
            
            change_rate = float(row.get('prdy_ctrt') or row.get('stck_vrss_rate') or 0)
            rate_text = f"{change_rate:+.2f}%"
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_change_rate", rate_text)
        except Exception as e:
            self.signal_emitter.error_signal.emit(f"종목 조회 오류: {str(e)}")

    def start_order_book_subscription(self, panel_id, symbol):
        """H0STASP0 실시간 호가 구독을 시작합니다."""
        if not symbol:
            return

        symbol = symbol.upper()
        self.order_symbols[panel_id] = symbol
        self.panel_by_symbol.setdefault(symbol, set()).add(panel_id)
        self.signal_emitter.update_signal.emit(f"panel{panel_id}_order_book_status", f"{symbol} 호가 구독 준비 중...")

        existing_items = ka.open_map.get(asking_price_krx.__name__, {}).get("items", [])
        if symbol not in existing_items:
            ka.KISWebSocket.subscribe(asking_price_krx, symbol, kwargs={"env_dv": "demo"})

        if self.order_book_active:
            return

        self.order_book_active = True
        self.ws_thread = threading.Thread(target=self.run_order_book_ws, daemon=True)
        self.ws_thread.start()

    def run_order_book_ws(self):
        try:
            ka.auth_ws(svr="vps", product="01")
            self.kws = ka.KISWebSocket(api_url="/tryitout")
            self.kws.start(on_result=self.on_ws_result, result_all_data=True)
        except Exception as e:
            self.signal_emitter.error_signal.emit(f"호가 구독 오류: {str(e)}")
            self.order_book_active = False
            self.signal_emitter.update_signal.emit("order_book_status", "호가 구독 실패")

    def on_ws_result(self, ws, tr_id, df, meta):
        if tr_id != "H0STASP0":
            return

        if df is None or df.empty:
            return

        row = df.iloc[0]
        symbol = str(row.get("MKSC_SHRN_ISCD") or row.get("MKSC_SHRN_ISCD") or "").strip().upper()
        panel_ids = self.panel_by_symbol.get(symbol, set())
        if not panel_ids:
            return

        current_price = self.get_numeric_value(row.get("ANTC_CNPR") or row.get("STCK_PRC") or row.get("ANTC_CNPR"))
        if current_price is None:
            current_price = self.get_numeric_value(row.get("ASKP1") or row.get("BIDP1") or 0)

        unit = self.get_price_unit(current_price)
        change_rate = self.format_change_rate(row.get("ANTC_CNTG_PRDY_CTRT", "-"))

        ask_prices = [self.get_numeric_value(row.get(f"ASKP{i}")) for i in range(1, 11)]
        ask_qtys = [self.format_price(row.get(f"ASKP_RSQN{i}")) for i in range(1, 11)]
        bid_prices = [self.get_numeric_value(row.get(f"BIDP{i}")) for i in range(1, 11)]
        bid_qtys = [self.format_price(row.get(f"BIDP_RSQN{i}")) for i in range(1, 11)]

        for panel_id in panel_ids:
            self.current_price_values[panel_id] = current_price
            for idx in range(self.order_book_depth):
                if idx == self.current_price_index:
                    price_label = self.format_price(current_price)
                    price_color = "black"
                    ask_qty = ""
                    bid_qty = ""
                    row_change_rate = change_rate
                elif idx < self.current_price_index:
                    level = self.current_price_index - idx
                    ask_price = ask_prices[level - 1] if 1 <= level <= len(ask_prices) else None
                    price_value = ask_price if ask_price is not None else current_price + level * unit
                    price_color = "red"
                    ask_qty = ask_qtys[level - 1] if ask_price is not None else ""
                    bid_qty = ""
                    row_change_rate = change_rate
                    price_label = self.format_price(price_value)
                else:
                    level = idx - self.current_price_index
                    bid_price = bid_prices[level - 1] if 1 <= level <= len(bid_prices) else None
                    price_value = bid_price if bid_price is not None else current_price - level * unit
                    price_color = "blue"
                    ask_qty = ""
                    bid_qty = bid_qtys[level - 1] if bid_price is not None else ""
                    row_change_rate = change_rate
                    price_label = self.format_price(price_value)

                self.signal_emitter.update_signal.emit(f"panel{panel_id}_price_{idx + 1}", f"{price_label}|{price_color}")
                self.signal_emitter.update_signal.emit(f"panel{panel_id}_ask_qty_{idx + 1}", ask_qty)
                self.signal_emitter.update_signal.emit(f"panel{panel_id}_bid_qty_{idx + 1}", bid_qty)
                self.signal_emitter.update_signal.emit(f"panel{panel_id}_change_rate_{idx + 1}", row_change_rate)

            self.signal_emitter.update_signal.emit(
                f"panel{panel_id}_order_book_summary",
                f"누적거래량: {row.get('ACML_VOL', '-')}, 매도잔량: {row.get('TOTAL_ASKP_RSQN', '-')}, 매수잔량: {row.get('TOTAL_BIDP_RSQN', '-')}",
            )
            self.signal_emitter.update_signal.emit(f"panel{panel_id}_order_book_status", f"{symbol} 호가 수신 중")

    def format_price(self, value):
        if value is None:
            return "-"
        try:
            return f"{int(value):,}"
        except Exception:
            return str(value)

    def format_change_rate(self, value):
        if value is None:
            return "-"
        try:
            rate = float(value)
            return f"{rate:+.2f}%"
        except Exception:
            return str(value)

    def get_numeric_value(self, value):
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('원', '').strip()
            return int(float(value))
        except Exception:
            return None

    def get_price_unit(self, price):
        if price is None:
            return 1
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

    def handle_click(self, panel_id, role, index, side):
        try:
            panel = self.order_panels.get(panel_id)
            if panel is None:
                return

            if index < 0 or index >= len(panel.get("price_labels", [])):
                self.log_message(f"[경고] 유효하지 않은 클릭 인덱스: {index}")
                return

            price = panel["price_labels"][index].text().strip()
            if not price or price == "-":
                self.log_message("[경고] 유효한 호가를 선택하세요.")
                return

            qty_input = panel.get("order_qty_input")
            qty = qty_input.text().strip() if qty_input is not None else ""
            qty = qty or self.default_order_qty
            if qty_input is not None:
                qty_input.setText(qty)

            symbol = self.order_symbols.get(panel_id) or panel["symbol_input"].text().strip().upper()
            if not symbol:
                self.log_message("[경고] 종목코드를 먼저 조회하세요.")
                return

            action_name = "매수" if role == "BUY" else "매도"
            confirm = QMessageBox.question(
                self,
                "주문 확인",
                f"{symbol} {action_name} {qty}주를 {price}원에 주문하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            order_key = f"{panel_id}_{role}_{price}"
            order_inputs = panel.get("ask_order_inputs") if side == "ask" else panel.get("bid_order_inputs")
            if not order_inputs or index < 0 or index >= len(order_inputs):
                self.log_message("[오류] 주문 필드가 올바르지 않습니다.")
                return

            order_input = order_inputs[index]
            if order_key in self.active_orders[panel_id]:
                confirm_cancel = QMessageBox.question(
                    self,
                    "취소 확인",
                    f"{symbol} {action_name} 주문을 취소하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm_cancel != QMessageBox.Yes:
                    return

                self.active_orders[panel_id].discard(order_key)
                order_input.setText("")
                order_input.setStyleSheet("background:#ffffff; color:#000000; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
                self.log_message(f"[취소] {symbol} {action_name} 취소: {price}원")
            else:
                self.active_orders[panel_id].add(order_key)
                order_input.setText(qty)
                active_style = "background:#ffd4d4; color:#000000;" if role == "BUY" else "background:#d4d4ff; color:#000000;"
                order_input.setStyleSheet(active_style + " border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
                self.log_message(f"[주문] {symbol} {action_name}: {price}원 / {qty}주")

            panel["order_message_label"].setText(f"{symbol} {action_name} {price}원 주문 요청")

            thread = threading.Thread(
                target=self.execute_order,
                args=(symbol, "buy" if role == "BUY" else "sell", qty, price),
                daemon=True,
            )
            thread.start()
        except Exception as e:
            self.log_message(f"[오류] 주문 필드 클릭 처리 실패: {str(e)}")

    def place_order(self):
        direction = self.order_direction_input.text().strip()
        quantity = self.order_qty_input.text().strip()
        price_text = self.order_price_input.text().strip()
        symbol = self.order_symbol or self.symbol_input.text().strip().upper()

        if not (direction and quantity and price_text and symbol):
            self.signal_emitter.error_signal.emit("종목, 매수/매도, 수량, 가격을 모두 입력하세요.")
            return

        if not quantity.isdigit() or int(quantity) <= 0:
            self.signal_emitter.error_signal.emit("올바른 주문수량을 입력하세요.")
            return

        price = price_text.replace(",", "").replace("원", "").strip()
        if not price.isdigit() or int(price) <= 0:
            self.signal_emitter.error_signal.emit("올바른 주문가격을 입력하세요.")
            return

        if direction in {"매수", "BUY"}:
            ord_dv = "buy"
            action_name = "매수"
        elif direction in {"매도", "SELL"}:
            ord_dv = "sell"
            action_name = "매도"
        else:
            self.signal_emitter.error_signal.emit("매수는 '매수' 또는 'BUY', 매도는 '매도' 또는 'SELL'로 입력하세요.")
            return

        self.order_message_label.setText(f"주문요청: {symbol} {action_name} {quantity}주 {int(price):,}원")
        self.log_message(f"[요청] {symbol} {action_name} {quantity}주 {int(price):,}원")

        thread = threading.Thread(
            target=self.execute_order,
            args=(symbol, ord_dv, str(int(quantity)), str(int(price))),
            daemon=True,
        )
        thread.start()

    def execute_order(self, symbol, ord_dv, quantity, price):
        try:
            result_df = dsf.order_cash(
                env_dv=self.order_env,
                ord_dv=ord_dv,
                cano=self.cano,
                acnt_prdt_cd=self.acnt_prdt_cd,
                pdno=symbol,
                ord_dvsn="00",
                ord_qty=quantity,
                ord_unpr=price,
                excg_id_dvsn_cd="KRX",
            )

            if result_df is None or result_df.empty:
                self.signal_emitter.error_signal.emit("주문 요청이 실패했습니다. API 응답이 없습니다.")
                return

            row = result_df.iloc[0]
            status_text = row.get('ord_stat') or row.get('ord_no') or row.get('acct_no') or "주문 접수"
            self.log_message(f"[완료] {symbol} {ord_dv} {quantity}주 {int(price):,}원 - {status_text}")
            panel_ids = self.panel_by_symbol.get(symbol, set())
            target_key = None
            for panel_id in panel_ids:
                self.signal_emitter.update_signal.emit(f"panel{panel_id}_order_book_status", f"{symbol} 주문 요청 완료")
            if not panel_ids:
                self.signal_emitter.update_signal.emit("order_book_status", f"{symbol} 주문 요청 완료")
        except Exception as e:
            self.signal_emitter.error_signal.emit(f"주문 실행 오류: {str(e)}")

    def clear_all_orders(self):
        self.active_orders.clear()
        for panel in self.order_panels.values():
            for order_input in panel.get("ask_order_inputs", []) + panel.get("bid_order_inputs", []):
                order_input.setText("")
                order_input.setStyleSheet("background:#ffffff; color:#000000; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
        self.log_message("[시스템] 모든 미체결 주문이 취소되었습니다.")

    def log_message(self, msg):
        self.log_box.append(msg)
        self.log_box.ensureCursorVisible()

    def update_dashboard(self, key, value):
        if key == "total_asset":
            self.total_asset_label.setText(value)
        elif key == "eval_asset":
            self.eval_asset_label.setText(value)
        elif key == "pending":
            self.pending_label.setText(value)
        elif key == "pnl":
            self.pnl_label.setText(value)
        elif key == "update_time":
            self.update_time_label.setText(value)
            return

        panel_id = None
        if key.startswith("panel"):
            parts = key.split("_", 2)
            if len(parts) >= 3 and parts[0].startswith("panel"):
                try:
                    panel_id = int(parts[0].replace("panel", ""))
                    key = parts[1] + ("_" + parts[2] if len(parts) == 3 else "")
                except ValueError:
                    panel_id = None

        panel = self.order_panels.get(panel_id) if panel_id is not None else None

        if key == "symbol_name" and panel is not None:
            panel["symbol_name_label"].setText(value)
            if panel.get("search_symbol_name_label") is not None:
                panel["search_symbol_name_label"].setText(value)
        elif key == "current_price" and panel is not None:
            panel["current_price_label"].setText(value)
        elif key == "open_price" and panel is not None:
            panel["open_price_label"].setText(value)
        elif key == "high_price" and panel is not None:
            panel["high_price_label"].setText(value)
        elif key == "low_price" and panel is not None:
            panel["low_price_label"].setText(value)
        elif key == "volume" and panel is not None:
            panel["volume_label"].setText(value)
        elif key == "change_rate" and panel is not None:
            panel["change_rate_label"].setText(value)
        elif key.startswith("price_") and panel is not None:
            idx = int(key.split("_")[1]) - 1
            if 0 <= idx < len(panel["price_labels"]):
                if "|" in value:
                    price_text, color = value.split("|", 1)
                else:
                    price_text, color = value, "black"
                panel["price_labels"][idx].setText(price_text)
                color_hex = "#000000"
                if color == "red":
                    color_hex = "#ff0000"
                elif color == "blue":
                    color_hex = "#0000ff"
                panel["price_labels"][idx].setStyleSheet(f"color:{color_hex}; background:#ffffff; border:1px solid #cccccc; font-size:9px; padding:0px; margin:0px;")
        elif key.startswith("ask_qty_") and panel is not None:
            idx = int(key.split("_")[1]) - 1
            if 0 <= idx < len(panel["ask_qty_labels"]):
                panel["ask_qty_labels"][idx].setText(value)
        elif key.startswith("bid_qty_") and panel is not None:
            idx = int(key.split("_")[1]) - 1
            if 0 <= idx < len(panel["bid_qty_labels"]):
                panel["bid_qty_labels"][idx].setText(value)
        elif key.startswith("change_rate_") and panel is not None:
            idx = int(key.split("_")[1]) - 1
            if 0 <= idx < len(panel["change_rate_labels"]):
                panel["change_rate_labels"][idx].setText(value)
        elif key == "order_book_status" and panel is not None:
            panel["order_status_label"].setText(value)
        elif key == "order_book_summary" and panel is not None:
            panel["order_summary_label"].setText(value)
        elif key == "order_book_status":
            # fallback for legacy single-panel updates
            for panel in self.order_panels.values():
                panel["order_status_label"].setText(value)
        elif key == "order_book_summary":
            for panel in self.order_panels.values():
                panel["order_summary_label"].setText(value)

    def periodic_update(self):
        """주기적 업데이트"""
        thread = threading.Thread(target=self.fetch_account_info)
        thread.daemon = True
        thread.start()
    
    def show_error(self, message):
        """오류 메시지 표시"""
        print(f"오류: {message}")


def main():
    app = QApplication(sys.argv)
    dashboard = AutoStockDashboard()
    dashboard.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
