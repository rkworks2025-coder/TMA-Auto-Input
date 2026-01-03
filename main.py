import sys
import os
import time
import datetime
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 設定エリア
# ==========================================
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

EVIDENCE_DIR = "evidence"

# ==========================================
# 厳格な操作関数群 (Fail Fast)
# ==========================================
def get_chrome_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1')
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def take_screenshot(driver, name):
    if not os.path.exists(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR)
    timestamp = datetime.datetime.now().strftime('%H%M%S')
    filename = f"{EVIDENCE_DIR}/{name}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"   [写] 保存: {filename}")
    except:
        print("   [写] 撮影失敗")

def click_strict(driver, selector_or_xpath):
    """クリックできなければ即死する"""
    if selector_or_xpath.startswith("/") or selector_or_xpath.startswith("("):
        by_method = By.XPATH
        sel = selector_or_xpath
    else:
        by_method = By.CSS_SELECTOR
        sel = selector_or_xpath if (selector_or_xpath.startswith("#") or "." in selector_or_xpath) else f"#{selector_or_xpath}"

    try:
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by_method, sel)))
        el.click()
        print(f"   [OK] Click: {sel}")
    except:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可: {sel}")

def input_strict(driver, selector_or_id, value):
    sel = selector_or_id if (selector_or_id.startswith("#") or "." in selector_or_id) else f"#{selector_or_id}"
    try:
        el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
        el.clear()
        el.send_keys(str(value))
        
        actual = el.get_attribute('value')
        if str(actual) != str(value):
            take_screenshot(driver, "ERROR_InputMismatch")
            raise Exception(f"入力値不一致: 期待({value}) != 実際({actual})")
        
        print(f"   [OK] Input: {value} -> {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        print(f"   [Error] 入力失敗: {sel}")
        raise e

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start ===")

    # 1. 引数取得（空文字でもOK）
    target_plate = sys.argv[1] if len(sys.argv) > 1 else ""
    
    # URL取得
    target_login_url = sys.argv[2] if (len(sys.argv) > 2 and sys.argv[2]) else DEFAULT_LOGIN_URL
    print(f"MODE: URL ({target_login_url})")

    driver = get_chrome_driver()

    try:
        # --- [1] ログイン ---
        print("\n--- [1] ログイン開始 ---")
        driver.get(target_login_url)
        take_screenshot(driver, "00_LoginPage")

        id_parts = TMA_ID.split("-")
        
        input_strict(driver, "#cardNo1", id_parts[0])
        input_strict(driver, "#cardNo2", id_parts[1])
        input_strict(driver, "#password", TMA_PW)
        
        click_strict(driver, ".btn-primary")
        
        # --- [1.5] メニュー画面遷移 ---
        print("\n--- [1.5] メニュー画面遷移 ---")
        try:
            # ★【修正】隠れメニュー回避: <main>タグの中にある「予約履歴」ボタンのみを対象にする
            # menu.html, 予約.html 共通
            menu_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]"))
            )
            print("   メニュー画面確認: 予約履歴ボタンをクリック")
            menu_btn.click()
        except:
            take_screenshot(driver, "ERROR_MenuPage")
            raise Exception("メニュー画面の『予約履歴』ボタンが見つかりません (メインエリア内にボタンはありますか？)")

        # --- [2] 車両リスト画面 ---
        print("\n--- [2] 車両リスト画面 ---")
        try:
            # ★【修正】隠れメニュー回避: <main>タグの中にある最初のリンク(車両)のみを対象にする
            # reserve.html, 予約.html 共通
            top_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "(//main//div[contains(@class,'main-contents')]//a)[1] | (//main//a)[1]"))
            )
            print("   リストの一番上を選択します")
            top_link.click()
        except:
             take_screenshot(driver, "ERROR_ListNotFound")
             raise Exception("車両リストが見つからないか、クリックできません")

        # 詳細画面が開いたことを確認
        try:
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#tireType1")))
        except:
            take_screenshot(driver, "ERROR_DetailNotLoaded")
            raise Exception("詳細画面への遷移に失敗しました")

        take_screenshot(driver, "01_VehicleSelected")

        # --- [3] データ取得 (ナンバーが空ならスキップ→デフォルト) ---
        print("\n--- [3] GASデータ取得 ---")
        tire_data = {}
        try:
            res = requests.get(f"{GAS_API_URL}?plate={target_plate}&check=1")
            j = res.json()
            if j.get("ok"):
                tire_data = j
        except:
            print("   通信エラーまたはデータなし（デフォルト値を使用）")

        # --- [4] 入力実行 (IDは実物HTMLと一致確認済み) ---
        print("\n--- [4] 入力実行 ---")
        
        click_strict(driver, "coolantGauge1")
        click_strict(driver, "engineOilGauge1")
        click_strict(driver, "washerFluidGauge1")

        click_strict(driver, "tireType1")
        
        # 値入力
        input_strict(driver, "tireFrontRegularPressure", tire_data.get("std_f", "240"))
        input_strict(driver, "tireRearRegularPressure", tire_data.get("std_r", "240"))
        
        prev = tire_data.get("prev", {})
        wheels = [("rf", "FrontRightCm"), ("lf", "FrontLeftCm"), ("lr", "RearLeftBi4"), ("rr", "RearRightBi4")]
        
        for pre, suf in wheels:
            # 製造週
            week = str(prev.get(f"dot_{pre}", "0123"))
            if len(week)==3: week = "0"+week
            input_strict(driver, f"tireMfr{suf}", week)
            
            # 溝
            depth = str(prev.get(f"tread_{pre}", "5.5"))
            ip, fp = (depth.split(".") + ["0"])[0:2]
            input_strict(driver, f"tireGroove{suf}Ip", ip)
            input_strict(driver, f"tireGroove{suf}Fp", fp[0])
            
            # 空気圧
            press = str(prev.get(f"pre_{pre}", "240"))
            input_strict(driver, f"tirePressure{suf}", press)
            input_strict(driver, f"tirePressureAdjusted{suf}", press)

        click_strict(driver, "tireDamage1")

        take_screenshot(driver, "02_InputResult")

        # その他項目（あればクリック）
        ids_ok = [
            "engineCondition1", "brakeCondition1", "parkingBrakeCondition1", 
            "washerSprayCondition1", "wiperWipeCondition1", "interiorDirt01", "exteriorDirt02"
        ]
        for i in ids_ok:
            try:
                # 存在確認だけして、あればクリック
                if len(driver.find_elements(By.ID, i)) > 0:
                     driver.find_element(By.ID, i).click()
            except:
                pass 

        # --- [5] 完了処理 ---
        print("\n--- [5] 完了処理 ---")
        tasks = ['daily', 'interior', 'wash', 'exterior', 'lend']
        for t in tasks:
            # JS関数があれば実行
            driver.execute_script(f"if(typeof completeTask === 'function') completeTask('{t}');")
            time.sleep(1)

        take_screenshot(driver, "03_PreComplete")
        
        try:
            # ★【修正】完了ボタンも <main> または 明確な完了ボタンクラスを狙う
            # 隠れメニューを避けるため、.btn-complete などの具体的クラスを優先
            finish_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "main a.is-complete, main .btn-complete, a.btn-complete"))
            )
            finish_btn.click()
            
            # アラート承認
            WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
            print("   完了アラート承認")
        except:
            print("   完了ボタンが見つからないか、JSで完了済み")

        print("\n=== SUCCESS: 全工程完了 ===")

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        raise e 
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
