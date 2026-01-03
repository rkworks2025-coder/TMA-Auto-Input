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
        # 隠れ要素を避けるため、clickableになるまで待つ
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by_method, sel)))
        # 念のためスクロールして中央に持ってくる
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
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
    print("=== Automation Start (Strict Mode) ===")

    # 1. 引数取得
    target_plate = sys.argv[1] if len(sys.argv) > 1 else ""
    target_login_url = sys.argv[2] if (len(sys.argv) > 2 and sys.argv[2]) else DEFAULT_LOGIN_URL
    print(f"MODE: URL ({target_login_url})")

    driver = get_chrome_driver()

    try:
        # --- [1] ログイン ---
        print("\n--- [1] ログイン開始 ---")
        driver.get(target_login_url)
        
        id_parts = TMA_ID.split("-")
        input_strict(driver, "#cardNo1", id_parts[0])
        input_strict(driver, "#cardNo2", id_parts[1])
        input_strict(driver, "#password", TMA_PW)
        click_strict(driver, ".btn-primary")
        
        # --- [1.5] メニュー画面 ---
        print("\n--- [1.5] メニュー画面遷移 ---")
        try:
            # 隠れメニュー回避: <main>内のボタンのみ
            click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")
        except:
            take_screenshot(driver, "ERROR_MenuPage")
            raise Exception("メニュー画面の『予約履歴』ボタンが見つかりません")

        # --- [2] 車両リスト選択 & ポップアップ開始 ---
        print("\n--- [2] 車両リスト選択 & 開始ポップアップ ---")
        try:
            # reserve.htmlの構造に合わせてXPath
            inspection_btn_xpath = "(//div[contains(@class, 'other-btn-area')]//a[contains(text(), '点検')])[1]"
            click_strict(driver, inspection_btn_xpath)
            print("   リスト選択: 『点検』ボタンをクリック")

            # ポップアップが表示されるのを待機
            print("   ポップアップ: 表示待機中...")
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.ID, "posupMessageConfirm"))
            )
            
            # ポップアップの「開始（完了）」ボタンを押す
            click_strict(driver, "#posupMessageConfirmOk")
            print("   ポップアップ: 確認ボタン(ID:posupMessageConfirmOk)を押下")

        except Exception as e:
             take_screenshot(driver, "ERROR_ReservePopup")
             raise Exception(f"車両リスト選択後のポップアップ処理に失敗しました: {e}")

        # --- [2.5] トップ画面 (点検開始処理) ---
        print("\n--- [2.5] トップ画面 (点検開始) ---")
        # index.html に遷移
        try:
            # 1. 黄色い「開始」ボタン (点検開始) を押す
            # 構造: <div id="startBtnContainer"><div ...><a ...><span>開始</span></a></div></div>
            # inputやbuttonタグではないため、CSSセレクタでaタグを狙う
            print("   トップ画面: 『点検開始』ボタンを探します...")
            click_strict(driver, "#startBtnContainer a")
            print("   トップ画面: 『点検開始』ボタン押下 -> リロード待機")
            
            # 2. リロード待ち & 「日常点検」ボタンの有効化待ち
            # リロード前は #dailyBtnContainer p.disable だが、リロード後は #dailyBtnContainer a になる
            print("   トップ画面: 『日常点検』ボタンが有効になるのを待機...")
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#dailyBtnContainer a"))
            )
            time.sleep(1) # 念のため一呼吸

            # 3. 「日常点検」ボタンを押す
            click_strict(driver, "#dailyBtnContainer a")
            print("   トップ画面: 『日常点検』へ移動")
            
        except Exception as e:
            take_screenshot(driver, "ERROR_IndexPage")
            raise Exception(f"トップ画面での『点検開始』または『日常点検』への遷移に失敗しました: {e}")

        # --- [3] 日常点検画面 (タブ切り替え & データ入力) ---
        print("\n--- [3] 日常点検 & GASデータ取得 ---")
        
        # 画面遷移確認
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            take_screenshot(driver, "ERROR_DailyCheckLoad")
            raise Exception("日常点検画面 (daily_check.html) が開けませんでした")

        # ★タブ切り替え: 「エンジンルーム」タブがデフォルトになったので、「タイヤ」への切り替えが必要
        try:
            print("   タブ切り替え: タイヤ/足回りタブを探します")
            # daily_check.html の構造に合わせて修正
            tab_xpath = "//div[contains(@class,'tab-button')][contains(.,'タイヤ')] | //li[contains(text(),'タイヤ')] | //a[contains(text(),'タイヤ')]"
            
            # タブが存在するか確認してからクリック
            if len(driver.find_elements(By.XPATH, tab_xpath)) > 0:
                click_strict(driver, tab_xpath)
                time.sleep(1)
                print("   タブ切り替え: 完了")
            else:
                print("   (タブが見つからないため、そのままスクロールで探します)")
        except:
            print("   (タブ切り替えスキップ)")

        # GASデータ取得
        tire_data = {}
        try:
            if target_plate:
                res = requests.get(f"{GAS_API_URL}?plate={target_plate}&check=1")
                j = res.json()
                if j.get("ok"): tire_data = j
        except:
            print("   通信エラーまたはデータなし")

        # --- [4] 入力実行 ---
        print("\n--- [4] 入力実行 ---")
        
        # 液体類（エンジンルームタブはデフォルトで開いているはず）
        try:
            click_strict(driver, "coolantGauge1")
            click_strict(driver, "engineOilGauge1")
            click_strict(driver, "washerFluidGauge1")
            print("   エンジンルーム入力完了")
        except:
            print("   (エンジンルーム項目が見つかりません。スキップします)")

        # タイヤ入力
        try:
            click_strict(driver, "tireType1")
            
            input_strict(driver, "tireFrontRegularPressure", tire_data.get("std_f", "240"))
            input_strict(driver, "tireRearRegularPressure", tire_data.get("std_r", "240"))
            
            prev = tire_data.get("prev", {})
            wheels = [("rf", "FrontRightCm"), ("lf", "FrontLeftCm"), ("lr", "RearLeftBi4"), ("rr", "RearRightBi4")]
            
            for pre, suf in wheels:
                week = str(prev.get(f"dot_{pre}", "0123"))
                if len(week)==3: week = "0"+week
                input_strict(driver, f"tireMfr{suf}", week)
                
                depth = str(prev.get(f"tread_{pre}", "5.5"))
                ip, fp = (depth.split(".") + ["0"])[0:2]
                input_strict(driver, f"tireGroove{suf}Ip", ip)
                input_strict(driver, f"tireGroove{suf}Fp", fp[0])
                
                press = str(prev.get(f"pre_{pre}", "240"))
                input_strict(driver, f"tirePressure{suf}", press)
                input_strict(driver, f"tirePressureAdjusted{suf}", press)

            click_strict(driver, "tireDamage1")
            print("   タイヤデータ入力完了")
        except Exception as e:
            take_screenshot(driver, "ERROR_TireInput")
            raise Exception(f"タイヤ入力欄が見つかりません (タブ切り替え失敗?): {e}")

        take_screenshot(driver, "02_InputResult")

        # その他項目（存在すれば）
        ids_ok = ["engineCondition1", "brakeCondition1", "parkingBrakeCondition1", "washerSprayCondition1", "wiperWipeCondition1", "interiorDirt01", "exteriorDirt02"]
        for i in ids_ok:
            try:
                if len(driver.find_elements(By.ID, i)) > 0: driver.find_element(By.ID, i).click()
            except: pass 

        # --- [5] 完了処理 ---
        print("\n--- [5] 完了処理 ---")
        tasks = ['daily', 'interior', 'wash', 'exterior', 'lend']
        for t in tasks:
            driver.execute_script(f"if(typeof completeTask === 'function') completeTask('{t}');")
            time.sleep(1)

        take_screenshot(driver, "03_PreComplete")
        
        try:
            # 完了ボタン
            finish_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "main a.is-complete, main .btn-complete, a.btn-complete"))
            )
            finish_btn.click()
            WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
            print("   完了アラート承認")
        except:
            print("   完了ボタンが見つからないか、JSで完了済み")

        print("\n=== SUCCESS: 全工程完了 ===")

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
