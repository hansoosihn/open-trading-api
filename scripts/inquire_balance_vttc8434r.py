#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VTTC8434R을 이용한 주식 잔고조회 예제
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples_user"))

import pandas as pd
import kis_auth as ka

# kis_auth에서 설정 가져오기
_cfg = ka.getEnv()

def main():
    # 1. 인증 처리
    print("=== KIS 인증 처리 ===")
    ka.auth(svr="vps", product="01")  # 모의투자 주식
    
    # 2. 계좌 정보 가져오기
    print("계좌번호: " + str(_cfg["my_paper_stock"]))
    print("계좌상품: 01")
    print()
    
    # 3. 주식 잔고조회 (VTTC8434R)
    print("=== 주식 잔고조회 (VTTC8434R) ===")
    try:
        # API 직접 호출
        api_url = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R"  # 모의투자 잔고조회
        
        cano = str(_cfg["my_paper_stock"])[:8]  # 종합계좌번호 8자리
        acnt_prdt_cd = "01"  # 계좌상품코드
        
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",  # 종목별 조회
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        print(f"계좌번호: {cano}")
        print(f"TR ID: {tr_id}")
        print(f"파라미터: {params}\n")
        
        res = ka._url_fetch(api_url, tr_id, "", params)
        
        if res.isOK():
            print("[응답 결과]")
            print(f"응답 코드: {res.getResCode()}")
            
            body = res.getBody()
            print(f"\n[잔고정보 (output1)]")
            if hasattr(body, 'output1') and body.output1:
                df1 = pd.DataFrame(body.output1)
                print(f"총 {len(df1)}개 종목")
                print(df1.to_string(index=False))
            else:
                print("보유 종목 없음")
            
            print(f"\n[계좌정보 (output2)]")
            if hasattr(body, 'output2') and body.output2:
                df2 = pd.DataFrame(body.output2)
                print(df2.to_string(index=False))
            else:
                print("계좌정보 없음")
        else:
            print("조회 실패")
            res.printError(url=api_url)
            
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
